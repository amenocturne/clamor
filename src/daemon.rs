use std::collections::{HashMap, HashSet, VecDeque};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::time::Duration;

use anyhow::{bail, Context, Result};
use portable_pty::{CommandBuilder, NativePtySystem, PtySize, PtySystem};
use tokio::net::UnixListener;
use tokio::sync::mpsc;

use crate::protocol::{recv_message_async, send_message_async, ClientMessage, DaemonAgent, DaemonMessage};

const RING_BUFFER_CAP: usize = 1024 * 1024;

pub fn daemon_socket_path() -> Result<PathBuf> {
    Ok(crate::config::FleetConfig::config_dir()?.join("fleet.sock"))
}

pub fn daemon_pid_path() -> Result<PathBuf> {
    Ok(crate::config::FleetConfig::config_dir()?.join("fleet.pid"))
}

pub fn is_daemon_running() -> bool {
    let pid_path = match daemon_pid_path() {
        Ok(p) => p,
        Err(_) => return false,
    };
    let pid_str = match std::fs::read_to_string(&pid_path) {
        Ok(s) => s,
        Err(_) => return false,
    };
    let pid: i32 = match pid_str.trim().parse() {
        Ok(p) => p,
        Err(_) => return false,
    };
    unsafe { libc::kill(pid, 0) == 0 }
}

pub fn start_daemon_background() -> Result<()> {
    let exe = std::env::current_exe().context("resolving fleet executable path")?;
    std::process::Command::new(exe)
        .arg("daemon")
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .context("spawning daemon process")?;

    std::thread::sleep(Duration::from_millis(200));
    Ok(())
}

enum PtyEvent {
    Output { id: String, data: Vec<u8> },
    Exited { id: String },
}

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
        let overflow = (self.ring_buffer.len() + data.len()).saturating_sub(RING_BUFFER_CAP);
        if overflow > 0 {
            self.ring_buffer.drain(..overflow);
        }
        self.ring_buffer.extend(data);
    }
}

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
    unsafe { libc::kill(-(child_pid as i32), libc::SIGINT) };
}

async fn send_to_client(stream: &mut tokio::net::UnixStream, msg: &DaemonMessage) -> bool {
    tokio::time::timeout(Duration::from_secs(5), send_message_async(stream, msg))
        .await
        .map_or(false, |r| r.is_ok())
}

pub async fn run_daemon() -> Result<()> {
    let sock_path = daemon_socket_path()?;
    let pid_path = daemon_pid_path()?;

    if let Some(parent) = sock_path.parent() {
        std::fs::create_dir_all(parent).context("creating ~/.fleet directory")?;
    }

    if sock_path.exists() {
        if is_daemon_running() {
            bail!("daemon already running (socket exists and PID is alive)");
        }
        let _ = std::fs::remove_file(&sock_path);
    }

    std::fs::write(&pid_path, std::process::id().to_string()).context("writing PID file")?;

    let listener = UnixListener::bind(&sock_path).context("binding Unix domain socket")?;

    let (pty_tx, mut pty_rx) = mpsc::channel::<PtyEvent>(1024);

    let mut agents: HashMap<String, AgentSlot> = HashMap::new();
    let mut client: Option<tokio::net::UnixStream> = None;
    let mut subscriptions: HashSet<String> = HashSet::new();
    let mut heartbeat_interval = tokio::time::interval(Duration::from_secs(30));

    loop {
        // Build a future that reads one client message, or pends forever if no client
        let client_read = async {
            match client {
                Some(ref mut stream) => recv_message_async::<ClientMessage, _>(stream).await,
                None => std::future::pending().await,
            }
        };

        tokio::select! {
            result = listener.accept() => {
                match result {
                    Ok((stream, _)) => {
                        subscriptions.clear();
                        client = Some(stream);
                    }
                    Err(e) => {
                        eprintln!("fleet-daemon: accept error: {e}");
                    }
                }
            }

            Some(evt) = pty_rx.recv() => {
                match evt {
                    PtyEvent::Output { id, data } => {
                        if let Some(slot) = agents.get_mut(&id) {
                            slot.push_output(&data);
                        }
                        if subscriptions.contains(&id) {
                            let mut disconnect = false;
                            if let Some(ref mut stream) = client {
                                let msg = DaemonMessage::Output { id, data };
                                if !send_to_client(stream, &msg).await {
                                    disconnect = true;
                                }
                            }
                            if disconnect {
                                client = None;
                                subscriptions.clear();
                            }
                        }
                    }
                    PtyEvent::Exited { id } => {
                        if let Some(slot) = agents.get_mut(&id) {
                            slot.alive = false;
                        }
                        let mut disconnect = false;
                        if let Some(ref mut stream) = client {
                            let msg = DaemonMessage::Exited { id };
                            if !send_to_client(stream, &msg).await {
                                disconnect = true;
                            }
                        }
                        if disconnect {
                            client = None;
                            subscriptions.clear();
                        }
                    }
                }
            }

            result = client_read => {
                match result {
                    Ok(msg) => {
                        let stream = client.as_mut().unwrap();
                        match handle_client_message(
                            msg, &mut agents, &mut subscriptions, stream, &pty_tx,
                        ).await {
                            HandleResult::Continue => {}
                            HandleResult::Shutdown => break,
                        }
                    }
                    Err(_) => {
                        client = None;
                        subscriptions.clear();
                    }
                }
            }

            _ = heartbeat_interval.tick() => {
                let mut disconnect = false;
                if let Some(ref mut stream) = client {
                    if !send_to_client(stream, &DaemonMessage::Heartbeat).await {
                        disconnect = true;
                    }
                }
                if disconnect {
                    client = None;
                    subscriptions.clear();
                }
            }
        }
    }

    let _ = std::fs::remove_file(&sock_path);
    let _ = std::fs::remove_file(&pid_path);

    Ok(())
}

enum HandleResult {
    Continue,
    Shutdown,
}

async fn handle_client_message(
    msg: ClientMessage,
    agents: &mut HashMap<String, AgentSlot>,
    subscriptions: &mut HashSet<String>,
    stream: &mut tokio::net::UnixStream,
    pty_tx: &mpsc::Sender<PtyEvent>,
) -> HandleResult {
    match msg {
        ClientMessage::Spawn {
            id,
            cwd,
            cmd,
            env,
            rows,
            cols,
        } => {
            match spawn_agent_pty(&id, &cwd, &cmd, &env, rows, cols, pty_tx) {
                Ok(slot) => {
                    agents.insert(id, slot);
                    let _ = send_to_client(stream, &DaemonMessage::Ok).await;
                }
                Err(e) => {
                    let _ = send_to_client(
                        stream,
                        &DaemonMessage::Error {
                            message: format!("{e:#}"),
                        },
                    )
                    .await;
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
                let _ = send_to_client(stream, &DaemonMessage::Ok).await;
            } else {
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::Error {
                        message: format!("unknown agent: {id}"),
                    },
                )
                .await;
            }
            HandleResult::Continue
        }
        ClientMessage::Sigint { id } => {
            if let Some(slot) = agents.get(&id) {
                if let Some(pid) = slot.child_pid {
                    send_sigint(pid);
                }
                let _ = send_to_client(stream, &DaemonMessage::Ok).await;
            } else {
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::Error {
                        message: format!("unknown agent: {id}"),
                    },
                )
                .await;
            }
            HandleResult::Continue
        }
        ClientMessage::Input { id, data } => {
            if let Some(slot) = agents.get_mut(&id) {
                let _ = slot.writer.write_all(&data);
                let _ = slot.writer.flush();
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
                let _ = send_to_client(stream, &DaemonMessage::Ok).await;
            } else {
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::Error {
                        message: format!("unknown agent: {id}"),
                    },
                )
                .await;
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
                )
                .await;
            } else {
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::Error {
                        message: format!("unknown agent: {id}"),
                    },
                )
                .await;
            }
            HandleResult::Continue
        }
        ClientMessage::Unsubscribe { id } => {
            subscriptions.remove(&id);
            let _ = send_to_client(stream, &DaemonMessage::Ok).await;
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
            let _ = send_to_client(stream, &DaemonMessage::AgentList { agents: list }).await;
            HandleResult::Continue
        }
        ClientMessage::Shutdown => {
            let _ = send_to_client(stream, &DaemonMessage::Ok).await;
            HandleResult::Shutdown
        }
        ClientMessage::Hello { version: _ } => {
            let _ = send_to_client(
                stream,
                &DaemonMessage::Hello {
                    version: env!("CARGO_PKG_VERSION").to_string(),
                },
            )
            .await;
            HandleResult::Continue
        }
        ClientMessage::Pong => HandleResult::Continue,
    }
}

fn spawn_agent_pty(
    id: &str,
    cwd: &str,
    cmd: &[String],
    env: &[(String, String)],
    rows: u16,
    cols: u16,
    pty_tx: &mpsc::Sender<PtyEvent>,
) -> Result<AgentSlot> {
    let pty_system = NativePtySystem::default();
    let pair = pty_system
        .openpty(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| anyhow::anyhow!("{e}"))?;

    let mut cmd_builder = if cmd.is_empty() {
        CommandBuilder::new(std::env::var("SHELL").unwrap_or_else(|_| "/bin/sh".into()))
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

    let tx = pty_tx.clone();
    let agent_id = id.to_string();
    let mut reader = pair
        .master
        .try_clone_reader()
        .map_err(|e| anyhow::anyhow!("{e}"))?;

    tokio::task::spawn_blocking(move || {
        let mut buf = [0u8; 65536];
        loop {
            match reader.read(&mut buf) {
                Ok(0) | Err(_) => {
                    let _ = tx.blocking_send(PtyEvent::Exited {
                        id: agent_id.clone(),
                    });
                    break;
                }
                Ok(n) => {
                    if tx
                        .blocking_send(PtyEvent::Output {
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
