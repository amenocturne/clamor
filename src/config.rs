use std::collections::HashMap;
use std::path::PathBuf;

use anyhow::Context;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClamorConfig {
    #[serde(default)]
    pub folders: HashMap<String, String>,
    #[serde(default)]
    pub dashboard: DashboardConfig,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum WatchMode {
    #[default]
    Fsevents,
    Poll,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DashboardConfig {
    #[serde(default = "default_refresh_interval")]
    pub refresh_interval: f64,
    #[serde(default)]
    pub watch_mode: WatchMode,
}

fn default_refresh_interval() -> f64 {
    1.0
}

impl Default for DashboardConfig {
    fn default() -> Self {
        Self {
            refresh_interval: default_refresh_interval(),
            watch_mode: WatchMode::default(),
        }
    }
}

impl Default for ClamorConfig {
    fn default() -> Self {
        Self {
            folders: HashMap::new(),
            dashboard: DashboardConfig::default(),
        }
    }
}

impl ClamorConfig {
    /// Returns `~/.clamor/`.
    pub fn config_dir() -> anyhow::Result<PathBuf> {
        let home = std::env::var("HOME").context("HOME environment variable not set")?;
        Ok(PathBuf::from(home).join(".clamor"))
    }

    /// Creates `~/.clamor/` if it doesn't exist.
    pub fn ensure_dir() -> anyhow::Result<()> {
        let dir = Self::config_dir()?;
        if !dir.exists() {
            std::fs::create_dir_all(&dir)
                .with_context(|| format!("Failed to create config dir: {}", dir.display()))?;
        }
        Ok(())
    }

    /// Loads config from `~/.clamor/config.json`.
    /// Creates a default config file if it doesn't exist.
    pub fn load() -> anyhow::Result<Self> {
        Self::ensure_dir()?;
        let path = Self::config_dir()?.join("config.json");

        if !path.exists() {
            let config = Self::default();
            let json = serde_json::to_string_pretty(&config)
                .context("Failed to serialize default config")?;
            std::fs::write(&path, json)
                .with_context(|| format!("Failed to write default config to {}", path.display()))?;
            return Ok(config);
        }

        let contents = std::fs::read_to_string(&path)
            .with_context(|| format!("Failed to read config from {}", path.display()))?;

        serde_json::from_str(&contents)
            .with_context(|| format!("Failed to parse config from {}", path.display()))
    }
}

/// Resolve a folder path, expanding `~`.
pub fn resolve_path(path: &str) -> PathBuf {
    if path.starts_with('~') {
        std::env::var("HOME")
            .map(|home| PathBuf::from(path.replacen('~', &home, 1)))
            .unwrap_or_else(|_| PathBuf::from(path))
    } else {
        PathBuf::from(path)
    }
}
