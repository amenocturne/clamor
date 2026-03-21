use std::collections::{HashMap, HashSet, VecDeque};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::time::Duration;

use anyhow::{bail, Context, Result};
use portable_pty::{CommandBuilder, NativePtySystem, PtySize, PtySystem};
use tokio::net::UnixListener;
use tokio::sync::mpsc;

use crate::protocol::{
    recv_message_async, send_message_async, ClientMessage, DaemonAgent, DaemonMessage,
};

const RING_BUFFER_CAP: usize = 1024 * 1024;

/// Buffers output between DEC 2026 synchronized update markers (BSU/ESU).
///
/// vt100 0.16.x doesn't support mode 2026. Claude Code (Ink) wraps each render
/// in `\x1b[?2026h` (BSU) and `\x1b[?2026l` (ESU). Instead of stripping them
/// and forwarding partial frames (which causes prompt jumping), we buffer all
/// output between BSU and ESU and forward the complete render atomically.
struct SyncOutputBuffer {
    buf: Vec<u8>,
    syncing: bool,
}

impl SyncOutputBuffer {
    fn new() -> Self {
        Self {
            buf: Vec::new(),
            syncing: false,
        }
    }

    /// Process incoming PTY data. Returns output chunks to forward.
    ///
    /// Outside BSU/ESU: passes through immediately.
    /// Inside BSU/ESU: buffers until ESU, then emits the complete frame.
    fn process(&mut self, data: &[u8]) -> Vec<Vec<u8>> {
        let mut outputs = Vec::new();
        let mut passthrough = Vec::new();
        let mut i = 0;

        while i < data.len() {
            if i + 8 <= data.len() {
                let window = &data[i..i + 8];
                if window == b"\x1b[?2026h" {
                    // BSU: flush any passthrough, start buffering
                    if !self.syncing && !passthrough.is_empty() {
                        outputs.push(std::mem::take(&mut passthrough));
                    }
                    self.syncing = true;
                    i += 8;
                    continue;
                }
                if window == b"\x1b[?2026l" {
                    // ESU: flush the synchronized frame
                    if self.syncing {
                        self.buf.extend_from_slice(&passthrough);
                        passthrough.clear();
                        if !self.buf.is_empty() {
                            outputs.push(std::mem::take(&mut self.buf));
                        }
                        self.syncing = false;
                    }
                    i += 8;
                    continue;
                }
            }
            passthrough.push(data[i]);
            i += 1;
        }

        if !passthrough.is_empty() {
            if self.syncing {
                self.buf.extend(passthrough);
            } else {
                outputs.push(passthrough);
            }
        }

        outputs
    }
}

pub fn daemon_socket_path() -> Result<PathBuf> {
    Ok(crate::config::ClamorConfig::config_dir()?.join("clamor.sock"))
}

pub fn daemon_pid_path() -> Result<PathBuf> {
    Ok(crate::config::ClamorConfig::config_dir()?.join("clamor.pid"))
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
    let exe = std::env::current_exe().context("resolving clamor executable path")?;
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
    QueryResponse { id: String, data: Vec<u8> },
}

/// Detects terminal capability queries in PTY output and generates responses.
///
/// Claude Code sends DA1, DSR, and DECRQM queries to detect terminal capabilities.
/// Without responses, it may fall back to degraded rendering paths.
struct TerminalQueryResponder {
    partial: Vec<u8>,
}

impl TerminalQueryResponder {
    fn new() -> Self {
        Self {
            partial: Vec::new(),
        }
    }

    /// Scan output data for terminal queries and return responses to write back.
    fn scan_for_queries(&mut self, data: &[u8]) -> Vec<u8> {
        let mut responses = Vec::new();
        let mut combined = std::mem::take(&mut self.partial);
        combined.extend_from_slice(data);

        let mut i = 0;
        while i < combined.len() {
            if combined[i] == 0x1b && i + 1 < combined.len() && combined[i + 1] == b'[' {
                if let Some((seq_len, response)) = Self::parse_csi_query(&combined[i..]) {
                    if let Some(resp) = response {
                        responses.extend_from_slice(&resp);
                    }
                    i += seq_len;
                    continue;
                } else {
                    // Incomplete sequence at end — buffer for next call
                    self.partial = combined[i..].to_vec();
                    return responses;
                }
            }
            i += 1;
        }

        responses
    }

    /// Try to parse a CSI query. Returns (length, optional_response).
    /// Returns None if the sequence appears incomplete.
    fn parse_csi_query(data: &[u8]) -> Option<(usize, Option<Vec<u8>>)> {
        if data.len() < 3 {
            return None;
        }

        // DA1: ESC [ c
        if data[2] == b'c' {
            return Some((3, Some(b"\x1b[?62;22c".to_vec())));
        }
        // DA1: ESC [ 0 c
        if data.len() >= 4 && data[2] == b'0' && data[3] == b'c' {
            return Some((4, Some(b"\x1b[?62;22c".to_vec())));
        }

        // DSR CPR: ESC [ 6 n — skip, do NOT respond with fake cursor position.
        // Claude Code uses the actual position for layout calculations.
        if data.len() >= 4 && data[2] == b'6' && data[3] == b'n' {
            return Some((4, None));
        }

        // DECRQM: ESC [ ? <digits> $ p
        if data.len() >= 4 && data[2] == b'?' {
            for j in 3..data.len().min(20) {
                if data[j] == b'$' && j + 1 < data.len() && data[j + 1] == b'p' {
                    let mode_str = std::str::from_utf8(&data[3..j]).unwrap_or("");
                    let mode_num = mode_str.parse::<u32>().unwrap_or(0);
                    // Report mode 2026 (synchronized output) as supported
                    let status = if mode_num == 2026 { 1 } else { 0 };
                    let resp = format!("\x1b[?{};{}$y", mode_num, status);
                    return Some((j + 2, Some(resp.into_bytes())));
                }
                if !data[j].is_ascii_digit() && data[j] != b'$' {
                    return Some((1, None)); // Not a query we handle
                }
            }
            return None; // Possibly incomplete
        }

        // Not a query — skip the ESC byte
        Some((1, None))
    }
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
        .is_ok_and(|r| r.is_ok())
}

pub async fn run_daemon() -> Result<()> {
    let sock_path = daemon_socket_path()?;
    let pid_path = daemon_pid_path()?;

    if let Some(parent) = sock_path.parent() {
        std::fs::create_dir_all(parent).context("creating ~/.clamor directory")?;
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
                        eprintln!("clamor-daemon: accept error: {e}");
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
                    PtyEvent::QueryResponse { id, data } => {
                        if let Some(slot) = agents.get_mut(&id) {
                            let _ = slot.writer.write_all(&data);
                            let _ = slot.writer.flush();
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
        let mut responder = TerminalQueryResponder::new();
        let mut sync_buf = SyncOutputBuffer::new();
        loop {
            match reader.read(&mut buf) {
                Ok(0) | Err(_) => {
                    let _ = tx.blocking_send(PtyEvent::Exited {
                        id: agent_id.clone(),
                    });
                    break;
                }
                Ok(n) => {
                    // Detect terminal queries and generate responses
                    let responses = responder.scan_for_queries(&buf[..n]);
                    if !responses.is_empty() {
                        let _ = tx.blocking_send(PtyEvent::QueryResponse {
                            id: agent_id.clone(),
                            data: responses,
                        });
                    }
                    // Buffer synchronized updates, forward complete frames
                    let chunks = sync_buf.process(&buf[..n]);
                    let mut broken = false;
                    for data in chunks {
                        if tx
                            .blocking_send(PtyEvent::Output {
                                id: agent_id.clone(),
                                data,
                            })
                            .is_err()
                        {
                            broken = true;
                            break;
                        }
                    }
                    if broken {
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
