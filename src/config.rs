use std::collections::HashMap;
use std::fmt;
use std::path::PathBuf;

use anyhow::Context;
use serde::de::{self, Visitor};
use serde::{Deserialize, Deserializer, Serialize, Serializer};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct ClamorConfig {
    #[serde(default)]
    pub folders: HashMap<String, String>,
    #[serde(default)]
    pub dashboard: DashboardConfig,
    #[serde(default)]
    pub theme: ThemeConfig,
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

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThemeConfig {
    /// Background for selected rows. Tune to be slightly lighter than your terminal bg.
    #[serde(default = "defaults::highlight")]
    pub highlight: RgbColor,
    /// Accent color: keybinding hints, borders, selection marker.
    #[serde(default = "defaults::accent")]
    pub accent: RgbColor,
    /// Status: working agents.
    #[serde(default = "defaults::status_working")]
    pub status_working: RgbColor,
    /// Status: agents waiting for input.
    #[serde(default = "defaults::status_input")]
    pub status_input: RgbColor,
    /// Status: finished agents.
    #[serde(default = "defaults::status_done")]
    pub status_done: RgbColor,
    /// Secondary text: durations, metadata.
    #[serde(default = "defaults::dimmed")]
    pub dimmed: RgbColor,
    /// Batch selection marker color.
    #[serde(default = "defaults::batch_marker")]
    pub batch_marker: RgbColor,
}

impl RgbColor {
    pub fn to_ratatui(self) -> ratatui::style::Color {
        ratatui::style::Color::Rgb(self.0[0], self.0[1], self.0[2])
    }
}

mod defaults {
    use super::RgbColor;
    pub fn highlight() -> RgbColor {
        RgbColor([50, 48, 58])
    }
    pub fn accent() -> RgbColor {
        RgbColor([0, 255, 255])
    } // cyan
    pub fn status_working() -> RgbColor {
        RgbColor([0, 255, 0])
    } // green
    pub fn status_input() -> RgbColor {
        RgbColor([255, 255, 0])
    } // yellow
    pub fn status_done() -> RgbColor {
        RgbColor([128, 128, 128])
    } // gray
    pub fn dimmed() -> RgbColor {
        RgbColor([128, 128, 128])
    } // gray
    pub fn batch_marker() -> RgbColor {
        RgbColor([255, 255, 0])
    } // yellow
}

impl Default for ThemeConfig {
    fn default() -> Self {
        Self {
            highlight: defaults::highlight(),
            accent: defaults::accent(),
            status_working: defaults::status_working(),
            status_input: defaults::status_input(),
            status_done: defaults::status_done(),
            dimmed: defaults::dimmed(),
            batch_marker: defaults::batch_marker(),
        }
    }
}

fn default_refresh_interval() -> f64 {
    1.0
}

/// RGB color that deserializes from either "#rrggbb" or [r, g, b].
#[derive(Debug, Clone, Copy)]
pub struct RgbColor(pub [u8; 3]);

impl Serialize for RgbColor {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        serializer.serialize_str(&format!(
            "#{:02x}{:02x}{:02x}",
            self.0[0], self.0[1], self.0[2]
        ))
    }
}

impl<'de> Deserialize<'de> for RgbColor {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct ColorVisitor;

        impl<'de> Visitor<'de> for ColorVisitor {
            type Value = RgbColor;

            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                write!(f, "hex color \"#rrggbb\" or RGB array [r, g, b]")
            }

            fn visit_str<E: de::Error>(self, v: &str) -> Result<RgbColor, E> {
                let hex = v.strip_prefix('#').unwrap_or(v);
                if hex.len() != 6 {
                    return Err(E::custom(format!(
                        "expected 6 hex digits, got {}",
                        hex.len()
                    )));
                }
                let r = u8::from_str_radix(&hex[0..2], 16).map_err(E::custom)?;
                let g = u8::from_str_radix(&hex[2..4], 16).map_err(E::custom)?;
                let b = u8::from_str_radix(&hex[4..6], 16).map_err(E::custom)?;
                Ok(RgbColor([r, g, b]))
            }

            fn visit_seq<A: de::SeqAccess<'de>>(self, mut seq: A) -> Result<RgbColor, A::Error> {
                let r = seq
                    .next_element()?
                    .ok_or_else(|| de::Error::invalid_length(0, &"3"))?;
                let g = seq
                    .next_element()?
                    .ok_or_else(|| de::Error::invalid_length(1, &"3"))?;
                let b = seq
                    .next_element()?
                    .ok_or_else(|| de::Error::invalid_length(2, &"3"))?;
                Ok(RgbColor([r, g, b]))
            }
        }

        deserializer.deserialize_any(ColorVisitor)
    }
}

impl Default for DashboardConfig {
    fn default() -> Self {
        Self {
            refresh_interval: default_refresh_interval(),
            watch_mode: WatchMode::default(),
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
