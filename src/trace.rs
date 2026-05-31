use std::fs::File;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use anyhow::Context;
use chrono::Utc;

use crate::config::TerminalBackend;
use crate::terminal_model::{CursorState, TerminalModel, TerminalModelState, TerminalModes};

pub const TRACE_DIR_ENV: &str = "CLAMOR_TRACE_DIR";

pub struct TraceRecorder {
    path: PathBuf,
    file: File,
}

impl TraceRecorder {
    pub fn from_env(agent_id: &str) -> anyhow::Result<Option<Self>> {
        let Some(dir) = std::env::var_os(TRACE_DIR_ENV) else {
            return Ok(None);
        };

        let dir = PathBuf::from(dir);
        std::fs::create_dir_all(&dir)
            .with_context(|| format!("creating trace dir {}", dir.display()))?;

        let safe_id = sanitize_file_component(agent_id);
        let stamp = Utc::now().format("%Y%m%dT%H%M%S%.3fZ");
        let path = dir.join(format!("{stamp}-{safe_id}.vt"));
        let file = File::create(&path)
            .with_context(|| format!("creating terminal trace {}", path.display()))?;

        Ok(Some(Self { path, file }))
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn record(&mut self, bytes: &[u8]) -> anyhow::Result<()> {
        self.file
            .write_all(bytes)
            .with_context(|| format!("writing terminal trace {}", self.path.display()))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReplaySummary {
    pub backend: TerminalBackend,
    pub bytes: usize,
    pub size: (u16, u16),
    pub cursor: CursorState,
    pub modes: TerminalModes,
    pub scrollback_len: usize,
    pub visible_text: String,
}

pub fn replay_trace(
    path: &Path,
    backend: TerminalBackend,
    rows: u16,
    cols: u16,
) -> anyhow::Result<ReplaySummary> {
    let mut bytes = Vec::new();
    File::open(path)
        .with_context(|| format!("opening terminal trace {}", path.display()))?
        .read_to_end(&mut bytes)
        .with_context(|| format!("reading terminal trace {}", path.display()))?;

    let mut terminal = TerminalModelState::new(backend, rows, cols, 50_000)?;
    terminal.process_output(&bytes);

    Ok(ReplaySummary {
        backend: terminal.backend(),
        bytes: bytes.len(),
        size: terminal.size(),
        cursor: terminal.cursor(),
        modes: terminal.modes(),
        scrollback_len: terminal.scrollback_len(),
        visible_text: terminal.visible_text(),
    })
}

fn sanitize_file_component(value: &str) -> String {
    let sanitized: String = value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_') {
                ch
            } else {
                '-'
            }
        })
        .collect();

    if sanitized.is_empty() {
        "agent".to_string()
    } else {
        sanitized
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitizes_trace_file_component() {
        assert_eq!(sanitize_file_component("abc/def:ghi"), "abc-def-ghi");
        assert_eq!(sanitize_file_component(""), "agent");
    }

    #[test]
    fn replays_raw_vt_trace() {
        let path = std::env::temp_dir().join(format!(
            "clamor-replay-test-{}-{}.vt",
            std::process::id(),
            Utc::now().timestamp_nanos_opt().unwrap_or_default()
        ));
        std::fs::write(&path, b"hello\r\nworld").unwrap();

        let summary = replay_trace(&path, TerminalBackend::Vt100, 3, 10).unwrap();

        assert_eq!(summary.bytes, 12);
        assert_eq!(summary.visible_text, "hello\nworld");

        let _ = std::fs::remove_file(path);
    }
}
