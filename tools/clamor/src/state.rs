use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};

use anyhow::Context;
use fs2::FileExt;
use serde::{Deserialize, Serialize};

use crate::agent::Agent;
use crate::config::ClamorConfig;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PromptHistoryEntry {
    pub title: String,
    pub description: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ClamorState {
    #[serde(default)]
    pub agents: HashMap<String, Agent>,
    #[serde(default)]
    pub prompt_history: Vec<PromptHistoryEntry>,
}

impl ClamorState {
    fn state_path() -> anyhow::Result<std::path::PathBuf> {
        Ok(ClamorConfig::config_dir()?.join("state.json"))
    }

    /// Reads state from `~/.clamor/state.json` with a shared (read) lock.
    /// Returns empty state if the file doesn't exist.
    pub fn load() -> anyhow::Result<Self> {
        let path = Self::state_path()?;

        if !path.exists() {
            return Ok(Self::default());
        }

        let file = File::open(&path)
            .with_context(|| format!("Failed to open state file: {}", path.display()))?;

        file.lock_shared()
            .context("Failed to acquire shared lock on state file")?;

        let mut contents = String::new();
        (&file)
            .read_to_string(&mut contents)
            .with_context(|| format!("Failed to read state file: {}", path.display()))?;

        file.unlock().context("Failed to unlock state file")?;

        if contents.trim().is_empty() {
            return Ok(Self::default());
        }

        serde_json::from_str(&contents)
            .with_context(|| format!("Failed to parse state file: {}", path.display()))
    }

    /// Writes state to `~/.clamor/state.json` with an exclusive file lock.
    #[allow(dead_code)]
    pub fn save(&self) -> anyhow::Result<()> {
        ClamorConfig::ensure_dir()?;
        let path = Self::state_path()?;

        let file = OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open(&path)
            .with_context(|| {
                format!("Failed to open state file for writing: {}", path.display())
            })?;

        file.lock_exclusive()
            .context("Failed to acquire lock on state file")?;

        let json = serde_json::to_string_pretty(self).context("Failed to serialize state")?;

        (&file)
            .write_all(json.as_bytes())
            .with_context(|| format!("Failed to write state file: {}", path.display()))?;

        file.unlock().context("Failed to unlock state file")?;

        Ok(())
    }
}

/// Atomic read-modify-write on the state file.
///
/// Acquires an exclusive lock, reads current state, applies `f`, writes back,
/// and releases the lock. Returns whatever `f` returns.
pub fn with_state<F, R>(f: F) -> anyhow::Result<R>
where
    F: FnOnce(&mut ClamorState) -> R,
{
    with_state_inner(f, true)
}

/// Like `with_state`, but non-blocking: returns Ok(None) if the lock can't be acquired.
/// Used by hooks to avoid blocking Claude Code.
pub fn try_with_state<F, R>(f: F) -> anyhow::Result<Option<R>>
where
    F: FnOnce(&mut ClamorState) -> R,
{
    match with_state_inner(f, false) {
        Ok(r) => Ok(Some(r)),
        Err(e) => {
            if let Some(io_err) = e.downcast_ref::<std::io::Error>() {
                if io_err.kind() == std::io::ErrorKind::WouldBlock {
                    return Ok(None);
                }
            }
            Err(e)
        }
    }
}

/// Async variant of `with_state` — runs the file-locked read-modify-write
/// on the tokio blocking thread pool to avoid stalling the async runtime.
#[allow(dead_code)]
pub async fn with_state_async<F, R>(f: F) -> anyhow::Result<R>
where
    F: FnOnce(&mut ClamorState) -> R + Send + 'static,
    R: Send + 'static,
{
    tokio::task::spawn_blocking(move || with_state(f)).await?
}

fn with_state_inner<F, R>(f: F, blocking: bool) -> anyhow::Result<R>
where
    F: FnOnce(&mut ClamorState) -> R,
{
    ClamorConfig::ensure_dir()?;
    let path = ClamorConfig::config_dir()?.join("state.json");

    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(&path)
        .with_context(|| format!("Failed to open state file: {}", path.display()))?;

    if blocking {
        file.lock_exclusive()
            .context("Failed to acquire lock on state file")?;
    } else {
        file.try_lock_exclusive()
            .context("Failed to acquire lock on state file (non-blocking)")?;
    }

    // Read current state (or default if empty/missing)
    let mut contents = String::new();
    (&file)
        .read_to_string(&mut contents)
        .with_context(|| format!("Failed to read state file: {}", path.display()))?;

    let mut state: ClamorState = if contents.trim().is_empty() {
        ClamorState::default()
    } else {
        serde_json::from_str(&contents)
            .with_context(|| format!("Failed to parse state file: {}", path.display()))?
    };

    // Apply the mutation
    let result = f(&mut state);

    // Write back — truncate first since we opened without truncate
    let json = serde_json::to_string_pretty(&state).context("Failed to serialize state")?;

    // Seek to beginning and truncate
    use std::io::Seek;
    (&file)
        .seek(std::io::SeekFrom::Start(0))
        .context("Failed to seek state file")?;
    file.set_len(0).context("Failed to truncate state file")?;

    (&file)
        .write_all(json.as_bytes())
        .with_context(|| format!("Failed to write state file: {}", path.display()))?;

    file.unlock().context("Failed to unlock state file")?;

    Ok(result)
}
