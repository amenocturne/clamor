use std::collections::{HashMap, VecDeque};
use std::io::{Read, Write};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::PathBuf;
use std::sync::mpsc;
use std::time::Duration;

use anyhow::{bail, Context, Result};
use portable_pty::{CommandBuilder, NativePtySystem, PtySize, PtySystem};

use crate::protocol::{ClientMessage, DaemonAgent, DaemonMessage};

/// Max ring buffer size per agent (~1MB).
const RING_BUFFER_CAP: usize = 1024 * 1024;

/// Path to the daemon's Unix domain socket.
pub fn daemon_socket_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string());
    PathBuf::from(home).join(".fleet").join("fleet.sock")
}

/// Path to the daemon's PID file.
pub fn daemon_pid_path() -> PathBuf {
    let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string());
    PathBuf::from(home).join(".fleet").join("fleet.pid")
}

/// Check whether a daemon process is currently running.
pub fn is_daemon_running() -> bool {
    let pid_path = daemon_pid_path();
    let pid_str = match std::fs::read_to_string(&pid_path) {
        Ok(s) => s,
        Err(_) => return false,
    };
    let pid: i32 = match pid_str.trim().parse() {
        Ok(p) => p,
        Err(_) => return false,
    };
    // Signal 0 checks if process exists without actually sending a signal
    unsafe { libc::kill(pid, 0) == 0 }
}

/// Start the daemon as a detached background process.
///
/// Spawns `fleet daemon` and returns once the child is launched.
/// The daemon will continue running after this process exits.
pub fn start_daemon_background() -> Result<()> {
    let exe = std::env::current_exe().context("resolving fleet executable path")?;
    std::process::Command::new(exe)
        .arg("daemon")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .context("spawning daemon process")?;

    // Brief wait for daemon to start listening
    std::thread::sleep(Duration::from_millis(200));
    Ok(())
}

/// Internal message from PTY reader threads to the main daemon loop.
enum PtyEvent {
    /// Output bytes from a PTY
    Output { id: String, data: Vec<u8> },
    /// PTY reader hit EOF (process exited)
    Exited { id: String },
}

/// Per-agent state tracked by the daemon.
struct AgentSlot {
    #[allow(dead_code)]
    master: Box<dyn portable_pty::MasterPty + Send>,
    writer: Box<dyn Write + Send>,
    child_pid: Option<u32>,
    ring_buffer: VecDeque<u8>,
    alive: bool,
}

impl AgentSlot {
    fn push_output(&mut self, data: &[u8]) {
        for &byte in data {
            if self.ring_buffer.len() >= RING_BUFFER_CAP {
                self.ring_buffer.pop_front();
            }
            self.ring_buffer.push_back(byte);
        }
    }
}

/// Send SIGINT to the foreground process group of a PTY child.
///
/// Finds children of the shell process and signals their process group.
/// Falls back to signaling the shell's own process group.
fn send_sigint(child_pid: u32) {
    if let Ok(output) = std::process::Command::new("pgrep")
        .args(["-P", &child_pid.to_string()])
        .output()
    {
        let children_str = String::from_utf8_lossy(&output.stdout);
        for line in children_str.lines() {
            if let Ok(cpid) = line.trim().parse::<i32>() {
                let pgid = unsafe { libc::getpgid(cpid) };
                if pgid > 0 {
                    unsafe { libc::kill(-pgid, libc::SIGINT) };
                    return;
                }
            }
        }
    }
    // Fallback: signal the shell's process group
    unsafe { libc::kill(-(child_pid as i32), libc::SIGINT) };
}

/// Send a DaemonMessage to a client, returning false if the write fails.
///
/// Temporarily sets the socket to blocking mode to ensure large messages
/// (like CatchUp with kilobytes of terminal output) are written completely.
fn send_to_client(stream: &mut UnixStream, msg: &DaemonMessage) -> bool {
    let _ = stream.set_nonblocking(false);
    let result = crate::protocol::send_message(stream, msg).is_ok();
    let _ = stream.set_nonblocking(true);
    result
}

/// Main daemon entry point. Blocks until shutdown.
///
/// Listens on a Unix domain socket, manages PTYs, and forwards output
/// to subscribed clients.
pub fn run_daemon() -> Result<()> {
    let sock_path = daemon_socket_path();
    let pid_path = daemon_pid_path();

    // Ensure ~/.fleet/ directory exists
    if let Some(parent) = sock_path.parent() {
        std::fs::create_dir_all(parent).context("creating ~/.fleet directory")?;
    }

    // Check for existing daemon
    if sock_path.exists() {
        if is_daemon_running() {
            bail!("daemon already running (socket exists and PID is alive)");
        }
        // Stale socket — remove it
        let _ = std::fs::remove_file(&sock_path);
    }

    // Write PID file
    std::fs::write(&pid_path, std::process::id().to_string())
        .context("writing PID file")?;

    let listener =
        UnixListener::bind(&sock_path).context("binding Unix domain socket")?;
    listener
        .set_nonblocking(true)
        .context("setting listener to non-blocking")?;

    let (pty_tx, pty_rx) = mpsc::channel::<PtyEvent>();

    let mut agents: HashMap<String, AgentSlot> = HashMap::new();
    let mut client: Option<UnixStream> = None;
    let mut subscriptions: std::collections::HashSet<String> =
        std::collections::HashSet::new();
    let mut shutdown = false;

    while !shutdown {
        // Accept new connections (non-blocking)
        match listener.accept() {
            Ok((stream, _)) => {
                // Replace existing client — single-user model
                stream
                    .set_nonblocking(true)
                    .ok();
                subscriptions.clear();
                client = Some(stream);
            }
            Err(ref e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
            Err(e) => {
                eprintln!("fleet-daemon: accept error: {e}");
            }
        }

        // Drain PTY events from reader threads
        while let Ok(evt) = pty_rx.try_recv() {
            match evt {
                PtyEvent::Output { id, data } => {
                    if let Some(slot) = agents.get_mut(&id) {
                        slot.push_output(&data);
                    }
                    if subscriptions.contains(&id) {
                        if let Some(ref mut stream) = client {
                            let msg = DaemonMessage::Output {
                                id: id.clone(),
                                data,
                            };
                            if !send_to_client(stream, &msg) {
                                client = None;
                                subscriptions.clear();
                            }
                        }
                    }
                }
                PtyEvent::Exited { id } => {
                    if let Some(slot) = agents.get_mut(&id) {
                        slot.alive = false;
                    }
                    if subscriptions.contains(&id) {
                        if let Some(ref mut stream) = client {
                            let msg = DaemonMessage::Exited { id };
                            if !send_to_client(stream, &msg) {
                                client = None;
                                subscriptions.clear();
                            }
                        }
                    }
                }
            }
        }

        // Read client messages (non-blocking)
        if let Some(ref mut stream) = client {
            loop {
                match crate::protocol::recv_message::<ClientMessage, _>(stream) {
                    Ok(msg) => match handle_client_message(
                        msg,
                        &mut agents,
                        &mut subscriptions,
                        stream,
                        &pty_tx,
                    ) {
                        HandleResult::Continue => {}
                        HandleResult::Shutdown => {
                            shutdown = true;
                            break;
                        }
                    },
                    Err(e) => {
                        let is_would_block = e
                            .downcast_ref::<std::io::Error>()
                            .map_or(false, |io_err| {
                                io_err.kind() == std::io::ErrorKind::WouldBlock
                            });
                        if !is_would_block {
                            // Client disconnected or protocol error
                            client = None;
                            subscriptions.clear();
                        }
                        break;
                    }
                }
            }
        }

        // Brief sleep to avoid busy-spinning
        std::thread::sleep(Duration::from_millis(5));
    }

    // Cleanup
    let _ = std::fs::remove_file(&sock_path);
    let _ = std::fs::remove_file(&pid_path);

    Ok(())
}

enum HandleResult {
    Continue,
    Shutdown,
}

fn handle_client_message(
    msg: ClientMessage,
    agents: &mut HashMap<String, AgentSlot>,
    subscriptions: &mut std::collections::HashSet<String>,
    stream: &mut UnixStream,
    pty_tx: &mpsc::Sender<PtyEvent>,
) -> HandleResult {
    match msg {
        ClientMessage::Spawn {
            id,
            cwd,
            cmd,
            env,
        } => {
            match spawn_agent_pty(&id, &cwd, &cmd, &env, pty_tx) {
                Ok(slot) => {
                    agents.insert(id, slot);
                    let _ = send_to_client(stream, &DaemonMessage::Ok);
                }
                Err(e) => {
                    let _ = send_to_client(
                        stream,
                        &DaemonMessage::Error {
                            message: format!("{e:#}"),
                        },
                    );
                }
            }
            HandleResult::Continue
        }
        ClientMessage::Kill { id } => {
            if let Some(slot) = agents.get_mut(&id) {
                if let Some(pid) = slot.child_pid {
                    unsafe { libc::kill(pid as i32, libc::SIGKILL) };
                }
                slot.alive = false;
                let _ = send_to_client(stream, &DaemonMessage::Ok);
            } else {
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::Error {
                        message: format!("unknown agent: {id}"),
                    },
                );
            }
            HandleResult::Continue
        }
        ClientMessage::Sigint { id } => {
            if let Some(slot) = agents.get(&id) {
                if let Some(pid) = slot.child_pid {
                    send_sigint(pid);
                }
                let _ = send_to_client(stream, &DaemonMessage::Ok);
            } else {
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::Error {
                        message: format!("unknown agent: {id}"),
                    },
                );
            }
            HandleResult::Continue
        }
        ClientMessage::Input { id, data } => {
            if let Some(slot) = agents.get_mut(&id) {
                let _ = slot.writer.write_all(&data);
                let _ = slot.writer.flush();
                // No response for Input — fire-and-forget for performance
            }
            HandleResult::Continue
        }
        ClientMessage::Resize { id, rows, cols } => {
            if let Some(slot) = agents.get_mut(&id) {
                let size = PtySize {
                    rows,
                    cols,
                    pixel_width: 0,
                    pixel_height: 0,
                };
                let _ = slot.master.resize(size);
                let _ = send_to_client(stream, &DaemonMessage::Ok);
            } else {
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::Error {
                        message: format!("unknown agent: {id}"),
                    },
                );
            }
            HandleResult::Continue
        }
        ClientMessage::Subscribe { id } => {
            if let Some(slot) = agents.get(&id) {
                let catch_up_data: Vec<u8> = slot.ring_buffer.iter().copied().collect();
                subscriptions.insert(id.clone());
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::CatchUp {
                        id,
                        data: catch_up_data,
                    },
                );
            } else {
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::Error {
                        message: format!("unknown agent: {id}"),
                    },
                );
            }
            HandleResult::Continue
        }
        ClientMessage::Unsubscribe { id } => {
            subscriptions.remove(&id);
            let _ = send_to_client(stream, &DaemonMessage::Ok);
            HandleResult::Continue
        }
        ClientMessage::List => {
            let list: Vec<DaemonAgent> = agents
                .iter()
                .map(|(id, slot)| DaemonAgent {
                    id: id.clone(),
                    alive: slot.alive,
                })
                .collect();
            let _ = send_to_client(stream, &DaemonMessage::AgentList { agents: list });
            HandleResult::Continue
        }
        ClientMessage::Shutdown => {
            let _ = send_to_client(stream, &DaemonMessage::Ok);
            HandleResult::Shutdown
        }
    }
}

/// Spawn a PTY for an agent and start a reader thread.
fn spawn_agent_pty(
    id: &str,
    cwd: &str,
    cmd: &[String],
    env: &[(String, String)],
    pty_tx: &mpsc::Sender<PtyEvent>,
) -> Result<AgentSlot> {
    let pty_system = NativePtySystem::default();
    let pair = pty_system
        .openpty(PtySize {
            rows: 24,
            cols: 80,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| anyhow::anyhow!("{e}"))?;

    let mut cmd_builder = if cmd.is_empty() {
        CommandBuilder::new("zsh")
    } else {
        let mut cb = CommandBuilder::new(&cmd[0]);
        for arg in &cmd[1..] {
            cb.arg(arg);
        }
        cb
    };
    cmd_builder.cwd(cwd);
    for (key, val) in env {
        cmd_builder.env(key, val);
    }

    let child = pair
        .slave
        .spawn_command(cmd_builder)
        .map_err(|e| anyhow::anyhow!("{e}"))?;
    let child_pid = child.process_id();
    drop(pair.slave);

    let writer = pair
        .master
        .take_writer()
        .map_err(|e| anyhow::anyhow!("{e}"))?;

    // Start reader thread
    let tx = pty_tx.clone();
    let agent_id = id.to_string();
    let mut reader = pair
        .master
        .try_clone_reader()
        .map_err(|e| anyhow::anyhow!("{e}"))?;

    std::thread::spawn(move || {
        let mut buf = [0u8; 65536];
        loop {
            match reader.read(&mut buf) {
                Ok(0) | Err(_) => {
                    let _ = tx.send(PtyEvent::Exited {
                        id: agent_id.clone(),
                    });
                    break;
                }
                Ok(n) => {
                    if tx
                        .send(PtyEvent::Output {
                            id: agent_id.clone(),
                            data: buf[..n].to_vec(),
                        })
                        .is_err()
                    {
                        break;
                    }
                }
            }
        }
    });

    // Keep the child handle alive by leaking it — the daemon manages lifetime
    // via the PID and signals, not the Child handle
    let _child = child;
    std::mem::forget(_child);

    Ok(AgentSlot {
        master: pair.master,
        writer,
        child_pid,
        ring_buffer: VecDeque::with_capacity(RING_BUFFER_CAP),
        alive: true,
    })
}
