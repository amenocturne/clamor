use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};

use anyhow::Context;
use fs2::FileExt;
use serde::{Deserialize, Serialize};

use crate::agent::Agent;
use crate::config::FleetConfig;

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct FleetState {
    #[serde(default)]
    pub agents: HashMap<String, Agent>,
}

impl FleetState {
    fn state_path(_config: &FleetConfig) -> std::path::PathBuf {
        FleetConfig::config_dir().join("state.json")
    }

    /// Reads state from `~/.fleet/state.json` with a shared (read) lock.
    /// Returns empty state if the file doesn't exist.
    pub fn load(config: &FleetConfig) -> anyhow::Result<Self> {
        let path = Self::state_path(config);

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

    /// Writes state to `~/.fleet/state.json` with an exclusive file lock.
    #[allow(dead_code)]
    pub fn save(&self, config: &FleetConfig) -> anyhow::Result<()> {
        FleetConfig::ensure_dir()?;
        let path = Self::state_path(config);

        let file = OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open(&path)
            .with_context(|| format!("Failed to open state file for writing: {}", path.display()))?;

        file.lock_exclusive()
            .context("Failed to acquire lock on state file")?;

        let json =
            serde_json::to_string_pretty(self).context("Failed to serialize state")?;

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
pub fn with_state<F, R>(_config: &FleetConfig, f: F) -> anyhow::Result<R>
where
    F: FnOnce(&mut FleetState) -> R,
{
    with_state_inner(f, true)
}

/// Like `with_state`, but non-blocking: returns Ok(None) if the lock can't be acquired.
/// Used by hooks to avoid blocking Claude Code.
pub fn try_with_state<F, R>(_config: &FleetConfig, f: F) -> anyhow::Result<Option<R>>
where
    F: FnOnce(&mut FleetState) -> R,
{
    match with_state_inner(f, false) {
        Ok(r) => Ok(Some(r)),
        Err(e) if e.to_string().contains("lock") => Ok(None),
        Err(e) => Err(e),
    }
}

fn with_state_inner<F, R>(f: F, blocking: bool) -> anyhow::Result<R>
where
    F: FnOnce(&mut FleetState) -> R,
{
    FleetConfig::ensure_dir()?;
    let path = FleetConfig::config_dir().join("state.json");

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

    let mut state: FleetState = if contents.trim().is_empty() {
        FleetState::default()
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
