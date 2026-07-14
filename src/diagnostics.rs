use std::fs::{File, OpenOptions};
use std::io::Write;
use std::os::fd::AsRawFd;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

use chrono::{Duration, Local, NaiveDate, Utc};

use crate::config::{ClamorConfig, TerminalLogLevel};

struct Logger {
    level: TerminalLogLevel,
    file: Mutex<File>,
}

static LOGGER: OnceLock<Logger> = OnceLock::new();

const TERMINAL_LOG_PREFIX: &str = "terminal-";
const TERMINAL_LOG_SUFFIX: &str = ".log";
const TERMINAL_LOG_RETENTION_DAYS: i64 = 7;

pub fn suppress_embedded_ghostty_logging() {
    // libghostty-vt inherits Ghostty's stderr logger, which corrupts Clamor's TUI.
    // Clamor terminal diagnostics are written separately to the runtime log file.
    std::env::set_var("GHOSTTY_LOG", "no-stderr,no-macos");
}

pub fn with_stderr_suppressed<T>(f: impl FnOnce() -> T) -> T {
    let Ok(dev_null) = OpenOptions::new().write(true).open("/dev/null") else {
        return f();
    };

    unsafe {
        let saved_stderr = libc::dup(libc::STDERR_FILENO);
        if saved_stderr < 0 {
            return f();
        }

        if libc::dup2(dev_null.as_raw_fd(), libc::STDERR_FILENO) < 0 {
            let _ = libc::close(saved_stderr);
            return f();
        }

        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(f));

        let _ = libc::dup2(saved_stderr, libc::STDERR_FILENO);
        let _ = libc::close(saved_stderr);

        match result {
            Ok(value) => value,
            Err(payload) => std::panic::resume_unwind(payload),
        }
    }
}

pub fn init_terminal_logging(level: TerminalLogLevel, component: &str) -> anyhow::Result<()> {
    let runtime_dir = ClamorConfig::runtime_dir()?;
    std::fs::create_dir_all(&runtime_dir)?;
    let today = Local::now().date_naive();
    migrate_legacy_terminal_log(&runtime_dir, today)?;
    prune_terminal_logs(&runtime_dir, today)?;

    if level == TerminalLogLevel::Off {
        return Ok(());
    }

    let path = terminal_log_path(&runtime_dir, today);
    let mut file = OpenOptions::new().create(true).append(true).open(&path)?;
    writeln!(
        file,
        "\n=== {} pid={} component={} level={:?} ===",
        Utc::now().to_rfc3339(),
        std::process::id(),
        component,
        level
    )?;

    let _ = LOGGER.set(Logger {
        level,
        file: Mutex::new(file),
    });

    Ok(())
}

fn terminal_log_path(runtime_dir: &Path, date: NaiveDate) -> PathBuf {
    runtime_dir.join(format!("{TERMINAL_LOG_PREFIX}{date}{TERMINAL_LOG_SUFFIX}"))
}

fn terminal_log_date(path: &Path) -> Option<NaiveDate> {
    let name = path.file_name()?.to_str()?;
    let date = name
        .strip_prefix(TERMINAL_LOG_PREFIX)?
        .strip_suffix(TERMINAL_LOG_SUFFIX)?;
    NaiveDate::parse_from_str(date, "%Y-%m-%d").ok()
}

fn migrate_legacy_terminal_log(runtime_dir: &Path, today: NaiveDate) -> anyhow::Result<()> {
    let legacy = runtime_dir.join("terminal.log");
    let dated = terminal_log_path(runtime_dir, today);
    if legacy.exists() && !dated.exists() {
        if let Err(err) = std::fs::rename(legacy, dated) {
            // Dashboard and daemon can start together and race this one-time
            // migration. If the other process moved the source first, the
            // desired state has already been reached.
            if err.kind() != std::io::ErrorKind::NotFound {
                return Err(err.into());
            }
        }
    }
    Ok(())
}

fn prune_terminal_logs(runtime_dir: &Path, today: NaiveDate) -> anyhow::Result<()> {
    let cutoff = today - Duration::days(TERMINAL_LOG_RETENTION_DAYS);
    for entry in std::fs::read_dir(runtime_dir)? {
        let entry = entry?;
        let path = entry.path();
        if entry.file_type()?.is_file()
            && terminal_log_date(&path).is_some_and(|date| date < cutoff)
        {
            if let Err(err) = std::fs::remove_file(path) {
                // Dashboard and daemon prune independently at startup. The
                // other process may remove the same expired file first.
                if err.kind() != std::io::ErrorKind::NotFound {
                    return Err(err.into());
                }
            }
        }
    }
    Ok(())
}

pub fn terminal_log(level: TerminalLogLevel, message: impl AsRef<str>) {
    let Some(logger) = LOGGER.get() else {
        return;
    };
    if level > logger.level || level == TerminalLogLevel::Off {
        return;
    }

    let Ok(mut file) = logger.file.lock() else {
        return;
    };
    let _ = writeln!(
        file,
        "{} [{level:?}] {}",
        Utc::now().to_rfc3339(),
        message.as_ref()
    );
}

pub fn terminal_log_enabled(level: TerminalLogLevel) -> bool {
    LOGGER
        .get()
        .is_some_and(|logger| level <= logger.level && level != TerminalLogLevel::Off)
}

pub fn byte_preview(bytes: &[u8]) -> String {
    const MAX_PREVIEW: usize = 160;
    let mut preview = String::new();

    for &byte in bytes.iter().take(MAX_PREVIEW) {
        match byte {
            b'\n' => preview.push_str("\\n"),
            b'\r' => preview.push_str("\\r"),
            b'\t' => preview.push_str("\\t"),
            0x1b => preview.push_str("\\x1b"),
            0x20..=0x7e => preview.push(byte as char),
            _ => preview.push_str(&format!("\\x{byte:02x}")),
        }
    }

    if bytes.len() > MAX_PREVIEW {
        preview.push_str("...");
    }

    preview
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_dir(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "clamor-diagnostics-{name}-{}-{}",
            std::process::id(),
            rand::random::<u64>()
        ))
    }

    #[test]
    fn daily_log_path_uses_calendar_date() {
        let date = NaiveDate::from_ymd_opt(2026, 7, 14).unwrap();
        assert_eq!(
            terminal_log_path(Path::new("/runtime"), date),
            Path::new("/runtime/terminal-2026-07-14.log")
        );
    }

    #[test]
    fn legacy_log_is_renamed_to_todays_log() {
        let dir = test_dir("legacy");
        std::fs::create_dir_all(&dir).unwrap();
        let today = NaiveDate::from_ymd_opt(2026, 7, 14).unwrap();
        let legacy = dir.join("terminal.log");
        let dated = terminal_log_path(&dir, today);
        std::fs::write(&legacy, b"history").unwrap();

        migrate_legacy_terminal_log(&dir, today).unwrap();

        assert!(!legacy.exists());
        assert_eq!(std::fs::read(&dated).unwrap(), b"history");
        std::fs::remove_dir_all(dir).unwrap();
    }

    #[test]
    fn startup_pruning_keeps_one_week_and_ignores_unrelated_files() {
        let dir = test_dir("retention");
        std::fs::create_dir_all(&dir).unwrap();
        let today = NaiveDate::from_ymd_opt(2026, 7, 14).unwrap();
        let expired = terminal_log_path(&dir, NaiveDate::from_ymd_opt(2026, 7, 6).unwrap());
        let boundary = terminal_log_path(&dir, NaiveDate::from_ymd_opt(2026, 7, 7).unwrap());
        let current = terminal_log_path(&dir, today);
        let unrelated = dir.join("state.json");
        for path in [&expired, &boundary, &current, &unrelated] {
            std::fs::write(path, b"test").unwrap();
        }

        prune_terminal_logs(&dir, today).unwrap();

        assert!(!expired.exists());
        assert!(boundary.exists());
        assert!(current.exists());
        assert!(unrelated.exists());
        std::fs::remove_dir_all(dir).unwrap();
    }
}
