use std::os::unix::net::UnixStream;

use anyhow::{Context, Result};

use crate::protocol::{
    send_message, recv_message, ClientMessage, DaemonAgent, DaemonMessage,
};

/// Client connection to the fleet daemon.
///
/// Communicates over a Unix domain socket using length-prefixed JSON messages.
pub struct DaemonClient {
    stream: UnixStream,
}

impl DaemonClient {
    /// Connect to the running daemon.
    pub fn connect() -> Result<Self> {
        let path = crate::daemon::daemon_socket_path();
        let stream = UnixStream::connect(&path)
            .with_context(|| format!("connecting to daemon at {}", path.display()))?;
        Ok(Self { stream })
    }

    /// Spawn a new agent PTY on the daemon.
    pub fn spawn_agent(
        &mut self,
        id: &str,
        cwd: &str,
        cmd: &[String],
        env: &[(String, String)],
    ) -> Result<()> {
        self.send(ClientMessage::Spawn {
            id: id.to_string(),
            cwd: cwd.to_string(),
            cmd: cmd.to_vec(),
            env: env.to_vec(),
        })?;
        self.expect_ok()
    }

    /// Kill an agent's PTY process.
    pub fn kill_agent(&mut self, id: &str) -> Result<()> {
        self.send(ClientMessage::Kill {
            id: id.to_string(),
        })?;
        self.expect_ok()
    }

    /// Send SIGINT to an agent's foreground process group.
    pub fn send_sigint(&mut self, id: &str) -> Result<()> {
        self.send(ClientMessage::Sigint {
            id: id.to_string(),
        })?;
        self.expect_ok()
    }

    /// Send raw input bytes to an agent's PTY.
    ///
    /// Fire-and-forget — the daemon does not respond to Input messages.
    pub fn send_input(&mut self, id: &str, data: &[u8]) -> Result<()> {
        self.send(ClientMessage::Input {
            id: id.to_string(),
            data: data.to_vec(),
        })
    }

    /// Resize an agent's PTY.
    pub fn resize(&mut self, id: &str, rows: u16, cols: u16) -> Result<()> {
        self.send(ClientMessage::Resize {
            id: id.to_string(),
            rows,
            cols,
        })?;
        self.expect_ok()
    }

    /// Subscribe to output from an agent. Returns the catch-up buffer.
    pub fn subscribe(&mut self, id: &str) -> Result<Vec<u8>> {
        self.send(ClientMessage::Subscribe {
            id: id.to_string(),
        })?;
        let msg: DaemonMessage = recv_message(&mut self.stream)?;
        match msg {
            DaemonMessage::CatchUp { data, .. } => Ok(data),
            DaemonMessage::Error { message } => {
                anyhow::bail!("subscribe failed: {message}")
            }
            other => anyhow::bail!("unexpected response: {other:?}"),
        }
    }

    /// Unsubscribe from an agent's output.
    pub fn unsubscribe(&mut self, id: &str) -> Result<()> {
        self.send(ClientMessage::Unsubscribe {
            id: id.to_string(),
        })?;
        self.expect_ok()
    }

    /// List all agents managed by the daemon.
    pub fn list_agents(&mut self) -> Result<Vec<DaemonAgent>> {
        self.send(ClientMessage::List)?;
        let msg: DaemonMessage = recv_message(&mut self.stream)?;
        match msg {
            DaemonMessage::AgentList { agents } => Ok(agents),
            DaemonMessage::Error { message } => {
                anyhow::bail!("list failed: {message}")
            }
            other => anyhow::bail!("unexpected response: {other:?}"),
        }
    }

    /// Request daemon shutdown.
    pub fn shutdown(&mut self) -> Result<()> {
        self.send(ClientMessage::Shutdown)?;
        self.expect_ok()
    }

    /// Try to read the next message from the daemon without blocking.
    ///
    /// Returns Ok(None) if no data is available (WouldBlock).
    /// The socket must be in non-blocking mode for this to work.
    pub fn try_recv(&mut self) -> Result<Option<DaemonMessage>> {
        match recv_message::<DaemonMessage, _>(&mut self.stream) {
            Ok(msg) => Ok(Some(msg)),
            Err(e) => {
                let is_would_block = e
                    .downcast_ref::<std::io::Error>()
                    .map_or(false, |io_err| {
                        io_err.kind() == std::io::ErrorKind::WouldBlock
                    });
                if is_would_block {
                    Ok(None)
                } else {
                    Err(e)
                }
            }
        }
    }

    /// Set the socket to non-blocking mode (for use in event loops).
    pub fn set_nonblocking(&mut self, nonblocking: bool) -> Result<()> {
        self.stream
            .set_nonblocking(nonblocking)
            .context("setting socket non-blocking mode")
    }

    fn send(&mut self, msg: ClientMessage) -> Result<()> {
        send_message(&mut self.stream, &msg)
    }

    fn expect_ok(&mut self) -> Result<()> {
        let msg: DaemonMessage = recv_message(&mut self.stream)?;
        match msg {
            DaemonMessage::Ok => Ok(()),
            DaemonMessage::Error { message } => anyhow::bail!("{message}"),
            other => anyhow::bail!("unexpected response: {other:?}"),
        }
    }
}
