use std::fs::{File, OpenOptions};
use std::io::Write;
use std::os::fd::AsRawFd;
use std::sync::{Mutex, OnceLock};

use chrono::Utc;

use crate::config::{ClamorConfig, TerminalLogLevel};

struct Logger {
    level: TerminalLogLevel,
    file: Mutex<File>,
}

static LOGGER: OnceLock<Logger> = OnceLock::new();

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
    if level == TerminalLogLevel::Off {
        return Ok(());
    }

    let path = ClamorConfig::runtime_dir()?.join("terminal.log");
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }

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
