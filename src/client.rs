use std::time::Duration;

use anyhow::{anyhow, Context, Result};
use tokio::net::UnixStream;

use crate::protocol::{
    recv_message_async, send_message_async, ClientMessage, DaemonAgent, DaemonMessage,
};

#[derive(Debug)]
pub struct SubscribeResult {
    pub catch_up: Vec<u8>,
    pub buffered: Vec<DaemonMessage>,
    pub terminal_backend: crate::config::TerminalBackend,
}

/// An error returned after messages were received while waiting for a parser
/// refresh response. The messages must be applied before reporting the error;
/// they are not included in the anyhow error chain so they cannot be lost.
#[derive(Debug)]
pub struct RefreshParserError {
    source: anyhow::Error,
    pub buffered: Vec<DaemonMessage>,
}

impl RefreshParserError {
    fn new(source: anyhow::Error, buffered: Vec<DaemonMessage>) -> Self {
        Self { source, buffered }
    }

    pub fn into_parts(self) -> (anyhow::Error, Vec<DaemonMessage>) {
        (self.source, self.buffered)
    }
}

impl std::fmt::Display for RefreshParserError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.source.fmt(f)
    }
}

impl std::error::Error for RefreshParserError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        self.source.source()
    }
}

pub struct DaemonClient {
    stream: UnixStream,
}

impl DaemonClient {
    pub async fn connect() -> Result<Self> {
        let path = crate::daemon::daemon_socket_path()?;
        let stream = UnixStream::connect(&path)
            .await
            .with_context(|| format!("connecting to daemon at {}", path.display()))?;
        Ok(Self { stream })
    }

    pub async fn spawn_agent(
        &mut self,
        id: &str,
        cwd: &str,
        cmd: &[String],
        env: &[(String, String)],
        rows: u16,
        cols: u16,
    ) -> Result<()> {
        self.send(ClientMessage::Spawn {
            id: id.to_string(),
            cwd: cwd.to_string(),
            cmd: cmd.to_vec(),
            env: env.to_vec(),
            rows,
            cols,
        })
        .await?;
        self.expect_ok().await
    }

    pub async fn kill_agent(&mut self, id: &str) -> Result<()> {
        self.send(ClientMessage::Kill { id: id.to_string() })
            .await?;
        self.expect_ok().await
    }

    pub async fn send_sigint(&mut self, id: &str) -> Result<()> {
        self.send(ClientMessage::Sigint { id: id.to_string() })
            .await?;
        self.expect_ok().await
    }

    pub async fn send_input(&mut self, id: &str, data: &[u8]) -> Result<()> {
        self.send(ClientMessage::Input {
            id: id.to_string(),
            data: data.to_vec(),
        })
        .await
    }

    /// Resize an agent and return any in-flight Output/Exited messages that
    /// arrived while waiting for the OK response, instead of discarding them.
    pub async fn resize_buffered(
        &mut self,
        id: &str,
        rows: u16,
        cols: u16,
    ) -> Result<Vec<DaemonMessage>> {
        self.send(ClientMessage::Resize {
            id: id.to_string(),
            rows,
            cols,
        })
        .await?;
        self.expect_ok_buffered().await
    }

    /// Subscribe to an agent and return catch-up data plus any in-flight
    /// Output/Exited messages that arrived while waiting for CatchUp.
    pub async fn subscribe_buffered(&mut self, id: &str) -> Result<SubscribeResult> {
        self.send(ClientMessage::Subscribe { id: id.to_string() })
            .await?;
        let mut buffered = Vec::new();
        loop {
            let msg: DaemonMessage =
                tokio::time::timeout(Duration::from_secs(5), recv_message_async(&mut self.stream))
                    .await
                    .context("subscribe timed out")??;

            match msg {
                DaemonMessage::CatchUp {
                    data,
                    terminal_backend,
                    ..
                } => {
                    return Ok(SubscribeResult {
                        catch_up: data,
                        buffered,
                        terminal_backend,
                    });
                }
                DaemonMessage::Error { message } => {
                    anyhow::bail!("subscribe failed: {message}")
                }
                DaemonMessage::Output { .. } | DaemonMessage::Exited { .. } => {
                    buffered.push(msg);
                }
                DaemonMessage::Heartbeat => continue,
                other => {
                    anyhow::bail!("unexpected response: {other:?}")
                }
            }
        }
    }

    /// Ask daemon to rebuild its parser from the ring buffer and send fresh
    /// catch-up data. Fixes accumulated rendering issues. Also ensures the
    /// subscription is active (same as subscribe).
    pub async fn refresh_parser_buffered(
        &mut self,
        id: &str,
    ) -> std::result::Result<SubscribeResult, RefreshParserError> {
        self.send(ClientMessage::RefreshParser { id: id.to_string() })
            .await
            .map_err(|error| RefreshParserError::new(error, Vec::new()))?;
        let mut buffered = Vec::new();
        loop {
            let msg: DaemonMessage = match tokio::time::timeout(
                Duration::from_secs(5),
                recv_message_async(&mut self.stream),
            )
            .await
            .context("refresh_parser timed out")
            {
                Ok(Ok(msg)) => msg,
                Ok(Err(error)) => return Err(RefreshParserError::new(error, buffered)),
                Err(error) => return Err(RefreshParserError::new(error, buffered)),
            };

            match msg {
                DaemonMessage::CatchUp {
                    id: catch_up_id,
                    data,
                    terminal_backend,
                } if catch_up_id == id => {
                    return Ok(SubscribeResult {
                        catch_up: data,
                        buffered,
                        terminal_backend,
                    });
                }
                DaemonMessage::CatchUp {
                    id: catch_up_id, ..
                } => {
                    let error = anyhow!(
                        "refresh_parser returned catch-up for agent {catch_up_id:?}, expected {id:?}"
                    );
                    return Err(RefreshParserError::new(error, buffered));
                }
                DaemonMessage::Error { message } => {
                    let error = anyhow!("refresh_parser failed: {message}");
                    return Err(RefreshParserError::new(error, buffered));
                }
                DaemonMessage::Output { .. } | DaemonMessage::Exited { .. } => {
                    buffered.push(msg);
                }
                DaemonMessage::Heartbeat => continue,
                other => {
                    let error = anyhow!("unexpected response: {other:?}");
                    return Err(RefreshParserError::new(error, buffered));
                }
            }
        }
    }

    /// Toggle an agent session between vt100 and ghostty parser backends.
    pub async fn toggle_terminal_backend_buffered(&mut self, id: &str) -> Result<SubscribeResult> {
        self.send(ClientMessage::ToggleTerminalBackend { id: id.to_string() })
            .await?;
        let mut buffered = Vec::new();
        loop {
            let msg: DaemonMessage =
                tokio::time::timeout(Duration::from_secs(5), recv_message_async(&mut self.stream))
                    .await
                    .context("toggle_terminal_backend timed out")??;

            match msg {
                DaemonMessage::CatchUp {
                    data,
                    terminal_backend,
                    ..
                } => {
                    return Ok(SubscribeResult {
                        catch_up: data,
                        buffered,
                        terminal_backend,
                    });
                }
                DaemonMessage::Error { message } => {
                    anyhow::bail!("toggle_terminal_backend failed: {message}")
                }
                DaemonMessage::Output { .. } | DaemonMessage::Exited { .. } => {
                    buffered.push(msg);
                }
                DaemonMessage::Heartbeat => continue,
                other => {
                    anyhow::bail!("unexpected response: {other:?}")
                }
            }
        }
    }

    pub async fn unsubscribe(&mut self, id: &str) -> Result<()> {
        self.send(ClientMessage::Unsubscribe { id: id.to_string() })
            .await?;
        self.expect_ok().await
    }

    pub async fn list_agents(&mut self) -> Result<Vec<DaemonAgent>> {
        self.send(ClientMessage::List).await?;
        loop {
            let msg: DaemonMessage =
                tokio::time::timeout(Duration::from_secs(5), recv_message_async(&mut self.stream))
                    .await
                    .context("list timed out")??;

            match msg {
                DaemonMessage::AgentList { agents } => return Ok(agents),
                DaemonMessage::Error { message } => {
                    anyhow::bail!("list failed: {message}")
                }
                DaemonMessage::Output { .. }
                | DaemonMessage::Exited { .. }
                | DaemonMessage::Heartbeat => continue,
                other => anyhow::bail!("unexpected response: {other:?}"),
            }
        }
    }

    pub async fn shutdown(&mut self) -> Result<()> {
        self.send(ClientMessage::Shutdown).await?;
        self.expect_ok().await
    }

    pub async fn recv(&mut self) -> Result<DaemonMessage> {
        recv_message_async(&mut self.stream).await
    }

    pub async fn pong(&mut self) -> Result<()> {
        self.send(ClientMessage::Pong).await
    }

    async fn send(&mut self, msg: ClientMessage) -> Result<()> {
        if send_message_async(&mut self.stream, &msg).await.is_ok() {
            return Ok(());
        }

        *self = Self::connect().await?;
        send_message_async(&mut self.stream, &msg).await
    }

    async fn expect_ok(&mut self) -> Result<()> {
        let _ = self.expect_ok_buffered().await?;
        Ok(())
    }

    async fn expect_ok_buffered(&mut self) -> Result<Vec<DaemonMessage>> {
        let mut buffered = Vec::new();
        loop {
            let msg: DaemonMessage =
                tokio::time::timeout(Duration::from_secs(5), recv_message_async(&mut self.stream))
                    .await
                    .context("expect_ok timed out")??;

            match msg {
                DaemonMessage::Ok => return Ok(buffered),
                DaemonMessage::Error { message } => anyhow::bail!("{message}"),
                DaemonMessage::Output { .. } | DaemonMessage::Exited { .. } => {
                    buffered.push(msg);
                }
                DaemonMessage::Heartbeat => continue,
                other => anyhow::bail!("unexpected response: {other:?}"),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::send_message_async;
    use tokio::net::UnixStream;

    async fn client_with_responses(responses: Vec<DaemonMessage>) -> DaemonClient {
        let (client_stream, mut server_stream) = UnixStream::pair().unwrap();
        tokio::spawn(async move {
            let _: ClientMessage = recv_message_async(&mut server_stream).await.unwrap();
            for response in responses {
                send_message_async(&mut server_stream, &response)
                    .await
                    .unwrap();
            }
        });
        DaemonClient {
            stream: client_stream,
        }
    }

    #[tokio::test]
    async fn refresh_parser_preserves_output_and_exit_before_error() {
        let mut client = client_with_responses(vec![
            DaemonMessage::Output {
                id: "agent-1".to_string(),
                data: b"still arriving".to_vec(),
            },
            DaemonMessage::Exited {
                id: "agent-1".to_string(),
            },
            DaemonMessage::Error {
                message: "agent disappeared".to_string(),
            },
        ])
        .await;

        let error = client.refresh_parser_buffered("agent-1").await.unwrap_err();
        let (source, buffered) = error.into_parts();
        assert_eq!(
            source.to_string(),
            "refresh_parser failed: agent disappeared"
        );
        assert!(matches!(buffered.as_slice(), [
            DaemonMessage::Output { id, data },
            DaemonMessage::Exited { id: exit_id },
        ] if id == "agent-1" && data == b"still arriving" && exit_id == "agent-1"));
    }

    #[tokio::test]
    async fn refresh_parser_rejects_mismatched_catch_up_and_preserves_buffered_messages() {
        let mut client = client_with_responses(vec![
            DaemonMessage::Output {
                id: "agent-1".to_string(),
                data: b"before wrong snapshot".to_vec(),
            },
            DaemonMessage::CatchUp {
                id: "agent-2".to_string(),
                data: b"wrong agent".to_vec(),
                terminal_backend: crate::config::TerminalBackend::Vt100,
            },
        ])
        .await;

        let error = client.refresh_parser_buffered("agent-1").await.unwrap_err();
        let (source, buffered) = error.into_parts();
        assert_eq!(
            source.to_string(),
            "refresh_parser returned catch-up for agent \"agent-2\", expected \"agent-1\""
        );
        assert!(matches!(buffered.as_slice(), [
            DaemonMessage::Output { id, data },
        ] if id == "agent-1" && data == b"before wrong snapshot"));
    }
}
