use std::collections::{HashMap, HashSet, VecDeque};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::time::{Duration, Instant};

use anyhow::{bail, Context, Result};
use portable_pty::{CommandBuilder, NativePtySystem, PtySize, PtySystem};
use tokio::net::UnixListener;
use tokio::sync::mpsc;

use crate::config::{ClamorConfig, TerminalBackend, TerminalLogLevel};
use crate::diagnostics::terminal_log;
use crate::protocol::{
    recv_message_async, send_message_async, ClientMessage, DaemonAgent, DaemonMessage,
};
use crate::render_prof::{RenderProfiler, Stage};
use crate::terminal_model::{
    terminal_repair_bytes, MouseEncoding, MouseMode, TerminalModel, TerminalModelState,
    TerminalModes,
};
use crate::trace::TraceRecorder;

pub fn daemon_socket_path() -> Result<PathBuf> {
    Ok(crate::config::ClamorConfig::runtime_dir()?.join("clamor.sock"))
}

pub fn daemon_pid_path() -> Result<PathBuf> {
    Ok(crate::config::ClamorConfig::runtime_dir()?.join("clamor.pid"))
}

pub fn daemon_hash_path() -> Result<PathBuf> {
    Ok(crate::config::ClamorConfig::runtime_dir()?.join("daemon.hash"))
}

fn current_exe_hash() -> Result<String> {
    let mut file =
        std::fs::File::open(std::env::current_exe().context("resolving clamor executable path")?)
            .context("opening clamor executable")?;
    let mut buf = [0u8; 8192];
    let mut hash = 0xcbf29ce484222325u64;

    loop {
        let read = file.read(&mut buf).context("reading clamor executable")?;
        if read == 0 {
            break;
        }
        for byte in &buf[..read] {
            hash ^= u64::from(*byte);
            hash = hash.wrapping_mul(0x100000001b3);
        }
    }

    Ok(format!("fnv1a64:{hash:016x}"))
}

pub fn is_running_daemon_current() -> Result<bool> {
    if !is_daemon_running() {
        return Ok(true);
    }

    let expected = current_exe_hash()?;
    let actual = match std::fs::read_to_string(daemon_hash_path()?) {
        Ok(hash) => hash,
        Err(_) => return Ok(false),
    };

    Ok(actual.trim() == expected)
}

pub fn ensure_daemon_current() -> Result<()> {
    if !is_daemon_running() {
        start_daemon_background()?;
        return Ok(());
    }

    if !is_running_daemon_current()? {
        bail!(
            "running Clamor daemon was started by a different build; run `clamor pre-upgrade` to stop it safely, then `clamor resume` after reinstalling"
        );
    }

    Ok(())
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
    /// Raw data from PTY reader. All processing (query detection, sync buffering,
    /// parser updates, CPR responses) happens daemon-side for correct ordering.
    RawData {
        id: String,
        data: Vec<u8>,
    },
    Exited {
        id: String,
    },
}

/// Detects terminal capability queries in PTY output and generates responses.
///
/// Claude Code sends DA1, DSR, and DECRQM queries to detect terminal capabilities.
/// Without responses, it may fall back to degraded rendering paths.
struct TerminalQueryResponder {
    partial: Vec<u8>,
    cpr_requested: bool,
}

#[derive(Default)]
struct TerminalModeTracker {
    partial: Vec<u8>,
    alternate_47: bool,
    alternate_1047: bool,
    alternate_1049: bool,
    mouse_9: bool,
    mouse_1000: bool,
    mouse_1002: bool,
    mouse_1003: bool,
    mouse_1005: bool,
    mouse_1006: bool,
    bracketed_paste: bool,
}

impl TerminalModeTracker {
    const MAX_PARTIAL_CSI_BYTES: usize = 128;

    fn process(&mut self, data: &[u8]) {
        let mut combined = std::mem::take(&mut self.partial);
        combined.extend_from_slice(data);

        let mut i = 0;
        while i < combined.len() {
            if combined[i] != 0x1b {
                i += 1;
                continue;
            }
            if i + 1 == combined.len() {
                self.partial.push(0x1b);
                return;
            }
            if combined[i + 1] == b'c' {
                self.reset_modes();
                i += 2;
                continue;
            }
            if combined[i + 1] != b'[' {
                i += 2;
                continue;
            }

            let Some(final_offset) = combined[i + 2..]
                .iter()
                .position(|byte| (0x40..=0x7e).contains(byte))
            else {
                let partial = &combined[i..];
                if partial.len() <= Self::MAX_PARTIAL_CSI_BYTES {
                    self.partial.extend_from_slice(partial);
                }
                return;
            };
            let final_index = i + 2 + final_offset;
            let final_byte = combined[final_index];
            if matches!(final_byte, b'h' | b'l') && combined.get(i + 2) == Some(&b'?') {
                let enabled = final_byte == b'h';
                for mode in combined[i + 3..final_index].split(|byte| *byte == b';') {
                    if let Ok(mode) = std::str::from_utf8(mode).unwrap_or("").parse::<u16>() {
                        self.set_private_mode(mode, enabled);
                    }
                }
            }
            i = final_index + 1;
        }
    }

    fn set_private_mode(&mut self, mode: u16, enabled: bool) {
        match mode {
            9 => self.mouse_9 = enabled,
            47 => self.alternate_47 = enabled,
            1000 => self.mouse_1000 = enabled,
            1002 => self.mouse_1002 = enabled,
            1003 => self.mouse_1003 = enabled,
            1005 => self.mouse_1005 = enabled,
            1006 => self.mouse_1006 = enabled,
            1047 => self.alternate_1047 = enabled,
            1049 => self.alternate_1049 = enabled,
            2004 => self.bracketed_paste = enabled,
            _ => {}
        }
    }

    fn reset_modes(&mut self) {
        self.alternate_47 = false;
        self.alternate_1047 = false;
        self.alternate_1049 = false;
        self.mouse_9 = false;
        self.mouse_1000 = false;
        self.mouse_1002 = false;
        self.mouse_1003 = false;
        self.mouse_1005 = false;
        self.mouse_1006 = false;
        self.bracketed_paste = false;
    }

    fn modes(&self) -> TerminalModes {
        let mouse_mode = if self.mouse_1003 {
            MouseMode::AnyMotion
        } else if self.mouse_1002 {
            MouseMode::ButtonMotion
        } else if self.mouse_1000 {
            MouseMode::PressRelease
        } else if self.mouse_9 {
            MouseMode::Press
        } else {
            MouseMode::None
        };
        let mouse_encoding = if self.mouse_1006 {
            MouseEncoding::Sgr
        } else if self.mouse_1005 {
            MouseEncoding::Utf8
        } else {
            MouseEncoding::Default
        };

        TerminalModes {
            alternate_screen: self.alternate_47 || self.alternate_1047 || self.alternate_1049,
            bracketed_paste: self.bracketed_paste,
            mouse_mode,
            mouse_encoding,
        }
    }
}

impl TerminalQueryResponder {
    fn new() -> Self {
        Self {
            partial: Vec::new(),
            cpr_requested: false,
        }
    }

    /// Scan output data for terminal queries and return responses to write back.
    /// CPR (cursor position) queries set `cpr_requested` — the caller handles
    /// the response after feeding the parser up to the CPR byte offset.
    fn scan_for_queries(&mut self, data: &[u8]) -> Vec<u8> {
        self.cpr_requested = false;
        let mut responses = Vec::new();
        let mut combined = std::mem::take(&mut self.partial);
        combined.extend_from_slice(data);

        let mut i = 0;
        while i < combined.len() {
            if combined[i] == 0x1b {
                if i + 1 >= combined.len() {
                    // Lone ESC at end — could be start of any escape sequence
                    self.partial = combined[i..].to_vec();
                    return responses;
                }
                if combined[i + 1] == b'[' {
                    // CPR check: ESC [ 6 n — set flag for deferred response
                    if i + 3 < combined.len() && combined[i + 2] == b'6' && combined[i + 3] == b'n'
                    {
                        self.cpr_requested = true;
                        i += 4;
                        continue;
                    }
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

        // DSR CPR (ESC [ 6 n) is handled in scan_for_queries via cpr_requested flag.

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

        // Unknown CSI — scan for a final byte (0x40-0x7E) to determine
        // if the sequence is complete. Without a final byte, it could be
        // a partially-received query (e.g. \x1b[6 waiting for 'n').
        for (j, &b) in data.iter().enumerate().take(64).skip(2) {
            if (0x40..=0x7e).contains(&b) {
                return Some((j + 1, None)); // Complete non-query, skip it
            }
        }
        None // No final byte yet — incomplete
    }
}

#[cfg(test)]
mod query_tests {
    use super::*;

    fn responder() -> TerminalQueryResponder {
        TerminalQueryResponder::new()
    }

    // ── CPR detection across split boundaries ──────────────────────────

    #[test]
    fn cpr_not_split() {
        let mut r = responder();
        let _ = r.scan_for_queries(b"Hello\x1b[6n world");
        assert!(r.cpr_requested);
    }

    #[test]
    fn cpr_split_esc() {
        // \x1b | [6n
        let mut r = responder();
        let _ = r.scan_for_queries(b"Hello\x1b");
        assert!(!r.cpr_requested);
        assert!(!r.partial.is_empty(), "lone ESC must be saved");
        let _ = r.scan_for_queries(b"[6n rest");
        assert!(r.cpr_requested);
    }

    #[test]
    fn cpr_split_esc_bracket() {
        // \x1b[ | 6n
        let mut r = responder();
        let _ = r.scan_for_queries(b"Hello\x1b[");
        assert!(!r.cpr_requested);
        assert!(!r.partial.is_empty());
        let _ = r.scan_for_queries(b"6n rest");
        assert!(r.cpr_requested);
    }

    #[test]
    fn cpr_split_esc_bracket_6() {
        // \x1b[6 | n — the originally-broken case
        let mut r = responder();
        let _ = r.scan_for_queries(b"Hello\x1b[6");
        assert!(!r.cpr_requested);
        assert!(!r.partial.is_empty(), "partial must be saved");
        let _ = r.scan_for_queries(b"n world");
        assert!(r.cpr_requested);
    }

    #[test]
    fn cpr_at_very_end_of_data() {
        let mut r = responder();
        let _ = r.scan_for_queries(b"\x1b[6n");
        assert!(r.cpr_requested);
        assert!(r.partial.is_empty());
    }

    // ── DA1 detection ──────────────────────────────────────────────────

    #[test]
    fn da1_basic() {
        let mut r = responder();
        let resp = r.scan_for_queries(b"\x1b[c");
        assert_eq!(resp, b"\x1b[?62;22c");
    }

    #[test]
    fn da1_variant_0c() {
        let mut r = responder();
        let resp = r.scan_for_queries(b"\x1b[0c");
        assert_eq!(resp, b"\x1b[?62;22c");
    }

    #[test]
    fn da1_split_esc_bracket() {
        // \x1b[ | c — partial saved, then completed
        let mut r = responder();
        let resp1 = r.scan_for_queries(b"\x1b[");
        assert!(resp1.is_empty(), "no response yet");
        assert!(!r.partial.is_empty());
        let resp2 = r.scan_for_queries(b"c");
        assert_eq!(resp2, b"\x1b[?62;22c");
    }

    #[test]
    fn da1_split_esc() {
        // \x1b | [c
        let mut r = responder();
        let _ = r.scan_for_queries(b"text\x1b");
        assert!(!r.partial.is_empty());
        let resp = r.scan_for_queries(b"[c more");
        assert_eq!(resp, b"\x1b[?62;22c");
    }

    // ── DECRQM detection ───────────────────────────────────────────────

    #[test]
    fn decrqm_mode_2026() {
        let mut r = responder();
        let resp = r.scan_for_queries(b"\x1b[?2026$p");
        // Mode 2026 → status 1 (supported)
        assert_eq!(resp, b"\x1b[?2026;1$y");
    }

    #[test]
    fn decrqm_unknown_mode() {
        let mut r = responder();
        let resp = r.scan_for_queries(b"\x1b[?9999$p");
        // Unknown mode → status 0
        assert_eq!(resp, b"\x1b[?9999;0$y");
    }

    #[test]
    fn decrqm_split_at_dollar() {
        // \x1b[?2026$ | p — partial saved at $, completed next read
        let mut r = responder();
        let resp1 = r.scan_for_queries(b"\x1b[?2026$");
        assert!(resp1.is_empty());
        assert!(!r.partial.is_empty());
        let resp2 = r.scan_for_queries(b"p");
        assert_eq!(resp2, b"\x1b[?2026;1$y");
    }

    #[test]
    fn decrqm_split_mid_digits() {
        // \x1b[?20 | 26$p
        let mut r = responder();
        let resp1 = r.scan_for_queries(b"\x1b[?20");
        assert!(resp1.is_empty());
        assert!(!r.partial.is_empty());
        let resp2 = r.scan_for_queries(b"26$p");
        assert_eq!(resp2, b"\x1b[?2026;1$y");
    }

    // ── Multiple queries in one read ───────────────────────────────────

    #[test]
    fn multiple_queries_one_read() {
        let mut r = responder();
        // DA1 + CPR + DECRQM all in one chunk
        let resp = r.scan_for_queries(b"\x1b[c\x1b[6n\x1b[?2026$p");
        assert!(r.cpr_requested);
        // Response should contain DA1 response + DECRQM response (CPR is deferred)
        let expected_da1 = b"\x1b[?62;22c";
        let expected_decrqm = b"\x1b[?2026;1$y";
        assert_eq!(resp.len(), expected_da1.len() + expected_decrqm.len());
        assert_eq!(&resp[..expected_da1.len()], expected_da1.as_slice());
        assert_eq!(&resp[expected_da1.len()..], expected_decrqm.as_slice());
    }

    #[test]
    fn cpr_between_normal_csi_sequences() {
        // SGR + CPR + cursor-move — CPR detected, non-queries skipped
        let mut r = responder();
        let resp = r.scan_for_queries(b"\x1b[31m\x1b[6n\x1b[H");
        assert!(r.cpr_requested);
        assert!(resp.is_empty(), "no DA1/DECRQM queries present");
    }

    // ── Incomplete CSI handling ────────────────────────────────────────

    #[test]
    fn incomplete_csi_saved_as_partial() {
        let mut r = responder();
        let _ = r.scan_for_queries(b"text\x1b[31");
        assert!(!r.partial.is_empty(), "incomplete CSI must be buffered");
    }

    #[test]
    fn complete_csi_not_saved() {
        let mut r = responder();
        let _ = r.scan_for_queries(b"text\x1b[31m");
        assert!(r.partial.is_empty(), "complete CSI must not leave partial");
    }

    #[test]
    fn incomplete_csi_completes_next_read() {
        // \x1b[31 | m — partial restored, sequence completed
        let mut r = responder();
        let _ = r.scan_for_queries(b"\x1b[31");
        assert!(!r.partial.is_empty());
        let _ = r.scan_for_queries(b"m text");
        assert!(r.partial.is_empty());
    }

    #[test]
    fn incomplete_csi_turns_into_cpr() {
        // \x1b[ at end, next read is 6n — reassembles as CPR
        let mut r = responder();
        let _ = r.scan_for_queries(b"content\x1b[");
        assert!(!r.partial.is_empty());
        let _ = r.scan_for_queries(b"6n");
        assert!(r.cpr_requested);
    }

    // ── Non-CSI escapes ────────────────────────────────────────────────

    #[test]
    fn non_csi_escape_not_saved_as_partial() {
        // \x1b] (OSC start) — not CSI, should not trigger partial save
        let mut r = responder();
        let _ = r.scan_for_queries(b"text\x1b]0;title\x07");
        assert!(r.partial.is_empty());
    }

    #[test]
    fn lone_esc_before_non_csi() {
        // \x1b at end, followed by ] — should save ESC then discard
        let mut r = responder();
        let _ = r.scan_for_queries(b"text\x1b");
        assert!(!r.partial.is_empty());
        let _ = r.scan_for_queries(b"]0;title\x07");
        assert!(r.partial.is_empty(), "non-CSI should clear partial");
    }

    // ── Edge cases ─────────────────────────────────────────────────────

    #[test]
    fn empty_data() {
        let mut r = responder();
        let resp = r.scan_for_queries(b"");
        assert!(resp.is_empty());
        assert!(!r.cpr_requested);
        assert!(r.partial.is_empty());
    }

    #[test]
    fn no_escape_sequences() {
        let mut r = responder();
        let resp = r.scan_for_queries(b"Hello world, no escapes here!");
        assert!(resp.is_empty());
        assert!(!r.cpr_requested);
        assert!(r.partial.is_empty());
    }

    #[test]
    fn cpr_resets_each_call() {
        let mut r = responder();
        let _ = r.scan_for_queries(b"\x1b[6n");
        assert!(r.cpr_requested);
        // Next call without CPR should reset the flag
        let _ = r.scan_for_queries(b"no cpr here");
        assert!(!r.cpr_requested);
    }

    #[test]
    fn partial_cleared_on_clean_data() {
        let mut r = responder();
        let _ = r.scan_for_queries(b"text\x1b[");
        assert!(!r.partial.is_empty());
        // Next call: partial + "H" → complete CSI (cursor home), partial cleared
        let _ = r.scan_for_queries(b"H more");
        assert!(r.partial.is_empty());
    }

    #[test]
    fn bsu_esc_sequence_not_false_cpr() {
        // BSU (\x1b[?2026h) contains no CPR — should not set cpr_requested
        let mut r = responder();
        let _ = r.scan_for_queries(b"\x1b[?2026h content \x1b[?2026l");
        assert!(!r.cpr_requested);
    }

    #[test]
    fn cpr_detected_inside_sync_frame() {
        // CPR query between BSU and ESU markers — correctly detected
        let mut r = responder();
        let _ = r.scan_for_queries(b"\x1b[?2026h\x1b[3;1Hcontent\x1b[6n\x1b[?2026l");
        assert!(r.cpr_requested, "CPR inside sync frame must be detected");
    }

    #[test]
    fn cpr_detected_when_bsu_split_across_reads() {
        // Read 1: BSU + content, Read 2: CPR + ESU
        // CPR in second read should be detected normally
        let mut r = responder();
        let _ = r.scan_for_queries(b"\x1b[?2026hcontent");
        assert!(!r.cpr_requested, "no CPR in first read");

        let _ = r.scan_for_queries(b"\x1b[6n\x1b[?2026l");
        assert!(r.cpr_requested, "CPR in second read must be detected");
    }
}

#[cfg(test)]
mod mode_tracker_tests {
    use super::*;
    use crate::terminal_model::Vt100TerminalModel;

    const CROSSTERM_MOUSE_ENABLE: &[u8] =
        b"\x1b[?1000h\x1b[?1002h\x1b[?1003h\x1b[?1015h\x1b[?1006h";
    const CROSSTERM_MOUSE_DISABLE: &[u8] =
        b"\x1b[?1006l\x1b[?1015l\x1b[?1003l\x1b[?1002l\x1b[?1000l";

    #[test]
    fn tracks_crossterm_mouse_capture_across_every_chunk_boundary() {
        for split in 0..=CROSSTERM_MOUSE_ENABLE.len() {
            let mut tracker = TerminalModeTracker::default();
            tracker.process(&CROSSTERM_MOUSE_ENABLE[..split]);
            tracker.process(&CROSSTERM_MOUSE_ENABLE[split..]);

            assert_eq!(
                tracker.modes().mouse_mode,
                MouseMode::AnyMotion,
                "split at byte {split}"
            );
            assert_eq!(
                tracker.modes().mouse_encoding,
                MouseEncoding::Sgr,
                "split at byte {split}"
            );
        }
    }

    #[test]
    fn tracks_mouse_capture_disable() {
        let mut tracker = TerminalModeTracker::default();
        tracker.process(CROSSTERM_MOUSE_ENABLE);
        tracker.process(CROSSTERM_MOUSE_DISABLE);

        assert_eq!(tracker.modes().mouse_mode, MouseMode::None);
        assert_eq!(tracker.modes().mouse_encoding, MouseEncoding::Default);
    }

    #[test]
    fn terminal_reset_clears_tracked_modes_across_chunk_boundaries() {
        for split in 0..=2 {
            let mut tracker = TerminalModeTracker::default();
            tracker.process(CROSSTERM_MOUSE_ENABLE);
            tracker.process(b"\x1b[?1049h\x1b[?2004h");
            tracker.process(&b"\x1bc"[..split]);
            tracker.process(&b"\x1bc"[split..]);

            assert_eq!(
                tracker.modes(),
                TerminalModes {
                    alternate_screen: false,
                    bracketed_paste: false,
                    mouse_mode: MouseMode::None,
                    mouse_encoding: MouseEncoding::Default,
                },
                "split at byte {split}"
            );
        }
    }

    #[test]
    fn tracks_mode_lists_and_alternate_screen_variants() {
        let mut tracker = TerminalModeTracker::default();
        tracker.process(b"\x1b[?47;2004;1002;1006h");

        assert_eq!(
            tracker.modes(),
            TerminalModes {
                alternate_screen: true,
                bracketed_paste: true,
                mouse_mode: MouseMode::ButtonMotion,
                mouse_encoding: MouseEncoding::Sgr,
            }
        );

        tracker.process(b"\x1b[?47;2004;1002;1006l");
        assert_eq!(
            tracker.modes(),
            TerminalModes {
                alternate_screen: false,
                bracketed_paste: false,
                mouse_mode: MouseMode::None,
                mouse_encoding: MouseEncoding::Default,
            }
        );
    }

    #[test]
    fn repair_preserves_mouse_mode_when_rebuild_tail_omits_enable() {
        let mut tracker = TerminalModeTracker::default();
        tracker.process(CROSSTERM_MOUSE_ENABLE);
        tracker.process(b"\x1b[?1049h\x1b[?2004h");

        // This models sync_terminal's bounded tail rebuild: the fresh parser
        // sees the latest repaint, but not Nefor's one-time setup sequences.
        let mut rebuilt = Vt100TerminalModel::new(24, 80, 0);
        rebuilt.process_output(b"\x1b[Hlatest frame");
        assert_eq!(rebuilt.modes().mouse_mode, MouseMode::None);

        let repair = terminal_repair_bytes(
            tracker.modes(),
            &rebuilt.contents_formatted(),
            rebuilt.cursor(),
        );
        let mut restored = Vt100TerminalModel::new(24, 80, 0);
        restored.process_catch_up(&repair);

        assert!(restored.modes().alternate_screen);
        assert!(restored.modes().bracketed_paste);
        assert_eq!(restored.modes().mouse_mode, MouseMode::AnyMotion);
        assert_eq!(restored.modes().mouse_encoding, MouseEncoding::Sgr);
    }
}

#[cfg(test)]
mod find_cpr_tests {
    use super::*;

    #[test]
    fn finds_cpr_at_start() {
        assert_eq!(find_cpr_offset(b"\x1b[6n rest"), Some(0));
    }

    #[test]
    fn finds_cpr_in_middle() {
        assert_eq!(find_cpr_offset(b"before\x1b[6n after"), Some(6));
    }

    #[test]
    fn no_cpr_in_data() {
        assert_eq!(find_cpr_offset(b"no cpr here"), None);
    }

    #[test]
    fn data_too_short() {
        assert_eq!(find_cpr_offset(b"\x1b[6"), None);
        assert_eq!(find_cpr_offset(b"\x1b["), None);
        assert_eq!(find_cpr_offset(b"\x1b"), None);
        assert_eq!(find_cpr_offset(b""), None);
    }

    #[test]
    fn finds_first_occurrence() {
        assert_eq!(find_cpr_offset(b"\x1b[6n\x1b[6n"), Some(0));
    }

    #[test]
    fn finds_cpr_between_bsu_and_esu() {
        // CPR query between DEC 2026 sync markers — detected at correct offset
        let data = b"\x1b[?2026hcontent\x1b[6n\x1b[?2026l";
        assert_eq!(find_cpr_offset(data), Some(15)); // after BSU (8) + "content" (7)
    }

    #[test]
    fn finds_cpr_after_cursor_move_in_sync_frame() {
        // Realistic scenario: BSU + cursor positioning + content + CPR
        let data = b"\x1b[?2026h\x1b[3;1HABCDEF\x1b[6n";
        let offset = find_cpr_offset(data).expect("CPR should be found");
        // BSU (8) + CUP (6) + "ABCDEF" (6) = 20
        assert_eq!(offset, 20);
        assert_eq!(&data[offset..offset + 4], b"\x1b[6n");
    }
}

/// Find the byte offset of `\x1b[6n` (CPR query) in data.
fn find_cpr_offset(data: &[u8]) -> Option<usize> {
    if data.len() < 4 {
        return None;
    }
    data.windows(4).position(|w| w == b"\x1b[6n")
}

const RING_BUFFER_CAP: usize = 4 * 1024 * 1024; // 4MB raw PTY history

/// Scrollback lines for the daemon's terminal model. This determines how
/// much scrollback the client gets on attach via catch-up repair bytes.
const DAEMON_SCROLLBACK: usize = 10_000;

/// Return the ring-buffer offset for incrementally replaying every byte the
/// terminal model is behind. `None` means ring-buffer eviction overtook the
/// parser and an exact incremental replay is no longer possible.
fn terminal_replay_start(total: usize, behind: usize) -> Option<usize> {
    total.checked_sub(behind)
}

fn replay_terminal_backlog(
    terminal: &mut TerminalModelState,
    ring_buffer: &VecDeque<u8>,
    behind: usize,
) -> Option<(usize, bool)> {
    let total = ring_buffer.len();
    let (replay_start, rebuilt) = match terminal_replay_start(total, behind) {
        Some(start) => (start, false),
        None => {
            let (rows, cols) = terminal.size();
            *terminal =
                TerminalModelState::new(terminal.backend(), rows, cols, DAEMON_SCROLLBACK).ok()?;
            (0, true)
        }
    };

    let replay: Vec<u8> = ring_buffer.iter().skip(replay_start).copied().collect();
    terminal.process_output(&replay);
    Some((replay.len(), rebuilt))
}

struct AgentSlot {
    #[allow(dead_code)]
    master: Box<dyn portable_pty::MasterPty + Send>,
    writer: Box<dyn Write + Send>,
    child_pid: Option<u32>,
    /// Raw output history — provides scrollback when client attaches.
    ring_buffer: VecDeque<u8>,
    /// Daemon-side terminal model — always holds the correct screen state.
    /// Appended after ring buffer in catch-up to fix the visible area.
    terminal: TerminalModelState,
    alive: bool,
    /// Bytes in ring buffer not yet processed by the terminal model.
    /// The terminal model is synced lazily before catch-up or CPR.
    terminal_behind: usize,
    /// Per-agent terminal query responder.
    responder: TerminalQueryResponder,
    /// DEC modes are state, not screen history. Track them on every PTY chunk
    /// so parser rebuilds from a bounded tail cannot forget one-time setup.
    mode_tracker: TerminalModeTracker,
    /// Optional raw PTY trace recorder for replay-based backend comparison.
    trace: Option<TraceRecorder>,
}

impl AgentSlot {
    /// Push sync-buffered output to the ring buffer (no parser update).
    fn push_ring_buffer(&mut self, data: &[u8]) {
        let overflow = (self.ring_buffer.len() + data.len()).saturating_sub(RING_BUFFER_CAP);
        if overflow > 0 {
            self.ring_buffer.drain(..overflow);
            skip_partial_escape(&mut self.ring_buffer);
            terminal_log(
                TerminalLogLevel::Warn,
                format!(
                    "daemon ring-buffer overflow dropped={} retained={} chunk={}",
                    overflow,
                    self.ring_buffer.len(),
                    data.len()
                ),
            );
        }
        self.ring_buffer.extend(data);
    }

    /// Rebuild the parser from scratch by replaying the ring buffer.
    /// Fixes accumulated rendering issues (parser state corruption, etc.).
    fn rebuild_parser(&mut self) {
        self.rebuild_parser_with_backend(self.terminal.backend());
    }

    fn toggle_terminal_backend(&mut self) {
        self.rebuild_parser_with_backend(self.terminal.backend().toggled());
    }

    fn rebuild_parser_with_backend(&mut self, backend: TerminalBackend) {
        let started = Instant::now();
        let (rows, cols) = self.terminal.size();
        let mut new_terminal = TerminalModelState::new(backend, rows, cols, DAEMON_SCROLLBACK)
            .expect("terminal backend should remain constructible");
        let buf: Vec<u8> = self.ring_buffer.iter().copied().collect();
        new_terminal.rebuild_from_history(&buf);
        self.terminal = new_terminal;
        self.terminal_behind = 0;
        terminal_log(
            TerminalLogLevel::Info,
            format!(
                "daemon rebuilt terminal backend={:?} size={}x{} replay_bytes={} scrollback={} elapsed_ms={}",
                self.terminal.backend(),
                rows,
                cols,
                buf.len(),
                self.terminal.scrollback_len(),
                started.elapsed().as_millis()
            ),
        );
    }

    /// Bring the terminal model up to date by replaying unprocessed ring
    /// buffer bytes. Called lazily before catch-up or CPR — not on the hot path.
    ///
    /// Terminal state is sequential: an arbitrary tail is not a valid recovery
    /// point because it can begin after a clear, inside an escape sequence, or
    /// without the alternate-screen state that gives later bytes meaning.
    fn sync_terminal(&mut self) {
        if self.terminal_behind == 0 {
            return;
        }
        let started = Instant::now();
        let total = self.ring_buffer.len();

        let Some((replay_len, rebuilt)) =
            replay_terminal_backlog(&mut self.terminal, &self.ring_buffer, self.terminal_behind)
        else {
            return;
        };
        self.terminal_behind = 0;
        terminal_log(
            if rebuilt {
                TerminalLogLevel::Info
            } else {
                TerminalLogLevel::Debug
            },
            format!(
                "daemon sync_terminal replayed={} total_ring={} rebuilt={} elapsed_ms={}",
                replay_len,
                total,
                rebuilt,
                started.elapsed().as_millis()
            ),
        );
    }

    /// Catch-up: ring buffer history + repair bytes. The client processes
    /// the ring buffer first (building scrollback from raw PTY history),
    /// then the repair bytes fix the final screen state.
    fn catch_up_data(&mut self) -> Vec<u8> {
        self.sync_terminal();
        let modes = self.mode_tracker.modes();
        let cursor = self.terminal.cursor();
        let formatted = self.terminal.contents_formatted();
        let repair = terminal_repair_bytes(modes, &formatted, cursor);

        // Prepend ring buffer so the client's parser builds scrollback
        // from the raw PTY history before the repair bytes fix the screen.
        let ring_len = self.ring_buffer.len();
        let mut data = Vec::with_capacity(ring_len + repair.len());
        data.extend(self.ring_buffer.iter());
        data.extend_from_slice(&repair);

        terminal_log(
            TerminalLogLevel::Debug,
            format!(
                "daemon catch-up backend={:?} ring={ring_len} repair={} total={} modes={:?}",
                self.terminal.backend(),
                repair.len(),
                data.len(),
                modes,
            ),
        );
        data
    }

    /// Process raw PTY data on the hot path. Skips ghostty-vt parsing —
    /// only scans for queries, pushes to ring buffer, and forwards to client.
    /// The terminal model is synced lazily when catch-up or CPR is needed.
    fn process_raw_data(&mut self, raw: &[u8]) -> Vec<Vec<u8>> {
        if let Some(trace) = self.trace.as_mut() {
            if let Err(err) = trace.record(raw) {
                eprintln!(
                    "clamor-daemon: disabling trace {}: {err:#}",
                    trace.path().display()
                );
                self.trace = None;
            }
        }

        self.mode_tracker.process(raw);

        // 1. Detect terminal queries (DA1, DECRQM, CPR)
        let responses = self.responder.scan_for_queries(raw);
        if !responses.is_empty() {
            let _ = self.writer.write_all(&responses);
            let _ = self.writer.flush();
        }

        // 2. Handle CPR: sync terminal and respond with accurate cursor
        if self.responder.cpr_requested {
            self.sync_terminal();
            if let Some(cpr_off) = find_cpr_offset(raw) {
                self.terminal.process_output(&raw[..cpr_off]);
                let cursor = self.terminal.cursor();
                let response = format!("\x1b[{};{}R", cursor.row + 1, cursor.col + 1);
                let _ = self.writer.write_all(response.as_bytes());
                let _ = self.writer.flush();
                self.terminal.process_output(&raw[cpr_off..]);
            } else {
                self.terminal.process_output(raw);
                let cursor = self.terminal.cursor();
                let response = format!("\x1b[{};{}R", cursor.row + 1, cursor.col + 1);
                let _ = self.writer.write_all(response.as_bytes());
                let _ = self.writer.flush();
            }
            // Terminal is now up to date — no behind bytes for this chunk
        } else {
            // Skip ghostty-vt parsing on the hot path
            self.terminal_behind += raw.len();
        }

        // 3. Push raw data to ring buffer
        self.push_ring_buffer(raw);

        // 4. Forward raw bytes to client
        vec![raw.to_vec()]
    }
}

#[cfg(test)]
mod catch_up_mode_tests {
    use super::*;
    use crate::terminal_model::{
        terminal_mode_prelude, CursorState, MouseEncoding, MouseMode, TerminalModes,
        Vt100TerminalModel,
    };

    #[test]
    fn large_lazy_backlog_keeps_repaint_that_precedes_last_512_kib() {
        const OLD_TAIL_CAP: usize = 512 * 1024;

        let mut backlog = b"\x1b[2J\x1b[Hcomplete nefor frame".to_vec();
        while backlog.len() <= OLD_TAIL_CAP * 2 {
            backlog.extend_from_slice(b"\x1b[H");
        }

        let mut incremental = Vt100TerminalModel::new(3, 40, 0);
        incremental.process_output(&backlog);

        let mut old_tail_rebuild = Vt100TerminalModel::new(3, 40, 0);
        old_tail_rebuild.process_output(&backlog[backlog.len() - OLD_TAIL_CAP..]);

        let ring: VecDeque<u8> = backlog.iter().copied().collect();
        let mut recovered = TerminalModelState::new(TerminalBackend::Vt100, 3, 40, 0).unwrap();
        let (replayed, rebuilt) = replay_terminal_backlog(&mut recovered, &ring, backlog.len())
            .expect("retained backlog should replay");

        assert!(incremental.visible_text().contains("complete nefor frame"));
        assert!(!old_tail_rebuild
            .visible_text()
            .contains("complete nefor frame"));
        assert_eq!(replayed, backlog.len());
        assert!(!rebuilt);
        assert_eq!(recovered.visible_text(), incremental.visible_text());
    }

    #[test]
    fn evicted_lazy_backlog_requires_full_retained_history_rebuild() {
        assert_eq!(
            terminal_replay_start(4 * 1024 * 1024, 5 * 1024 * 1024),
            None
        );
    }

    #[test]
    fn prelude_rehydrates_mouse_bracketed_paste_and_alt_screen() {
        let mut source = Vt100TerminalModel::new(24, 80, 0);
        source.process_output(b"\x1b[?1049h\x1b[?1002h\x1b[?1006h\x1b[?2004h");

        let prelude = terminal_mode_prelude(source.modes());
        let mut restored = vt100::Parser::new(24, 80, 0);
        restored.process(&prelude);

        assert!(restored.screen().alternate_screen());
        assert!(restored.screen().bracketed_paste());
        assert_eq!(
            restored.screen().mouse_protocol_mode(),
            vt100::MouseProtocolMode::ButtonMotion
        );
        assert_eq!(
            restored.screen().mouse_protocol_encoding(),
            vt100::MouseProtocolEncoding::Sgr
        );
    }

    #[test]
    fn snapshot_catch_up_contains_only_repair_bytes() {
        let modes = TerminalModes {
            alternate_screen: false,
            bracketed_paste: false,
            mouse_mode: MouseMode::None,
            mouse_encoding: MouseEncoding::Default,
        };
        let formatted = b"visible frame";
        let cursor = CursorState { row: 2, col: 3 };

        let data = terminal_repair_bytes(modes, formatted, cursor);

        // Starts with CAN (escape cancel)
        assert_eq!(data[0], 0x18);
        // Contains the formatted screen content
        assert!(data.windows(formatted.len()).any(|w| w == formatted));
        // Ends with cursor positioning
        assert!(data.ends_with(b"\x1b[3;4H"));
        // Does NOT contain raw ring buffer history
        assert!(!data.windows(b"history".len()).any(|w| w == b"history"));
    }

    #[test]
    fn prelude_clears_stale_modes_when_source_has_none() {
        let source = Vt100TerminalModel::new(24, 80, 0);
        let prelude = terminal_mode_prelude(source.modes());

        let mut restored = vt100::Parser::new(24, 80, 0);
        restored.process(b"\x1b[?1049h\x1b[?1003h\x1b[?1006h\x1b[?2004h");
        restored.process(&prelude);

        assert!(!restored.screen().alternate_screen());
        assert!(!restored.screen().bracketed_paste());
        assert_eq!(
            restored.screen().mouse_protocol_mode(),
            vt100::MouseProtocolMode::None
        );
        assert_eq!(
            restored.screen().mouse_protocol_encoding(),
            vt100::MouseProtocolEncoding::Default
        );
    }
}

/// After byte-level drain, skip past any partial escape sequence at the front.
///
/// Scans forward to find the first "safe" byte to start parsing from:
/// a newline, an ESC (start of a new sequence), or a byte after a CSI
/// final byte (0x40-0x7E) that terminates the partial sequence.
fn skip_partial_escape(buf: &mut VecDeque<u8>) {
    if buf.is_empty() {
        return;
    }
    // If the front byte is ESC, we're at a sequence boundary — nothing to skip.
    if buf.front() == Some(&0x1b) {
        return;
    }
    // If the front byte is a normal printable char or control that isn't
    // part of a CSI parameter/intermediate range, it's probably safe.
    // CSI parameters are 0x30-0x3F, intermediates are 0x20-0x2F.
    // If we see something outside those ranges (and not ESC), we're likely
    // at normal text already.
    if let Some(&front) = buf.front() {
        if front == 0x0a || front == 0x0d {
            return; // newline boundary
        }
        // If it doesn't look like mid-CSI, leave it alone
        if front >= 0x40 && front != 0x5b {
            // 0x40-0x7E are CSI final bytes or uppercase letters.
            // If we land on one, it terminates whatever partial sequence
            // preceded it — skip it and we're clean.
            buf.pop_front();
            return;
        }
    }
    // Likely mid-CSI (parameters/intermediates). Scan forward to the end
    // of the partial sequence or the next safe boundary.
    let is_csi_final = |b: u8| (0x40..=0x7e).contains(&b) && b != 0x5b;
    let skip_to = buf
        .iter()
        .position(|&b| b == 0x1b || b == 0x0a || b == 0x0d || is_csi_final(b));
    if let Some(pos) = skip_to {
        let skip = if buf.get(pos).is_some_and(|&b| is_csi_final(b)) {
            pos + 1 // skip past the final byte too
        } else {
            pos // stop before ESC/newline
        };
        buf.drain(..skip);
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
    let config = ClamorConfig::load()?;
    crate::diagnostics::init_terminal_logging(config.terminal.loglevel, "daemon")?;
    let terminal_backend = config.terminal.backend;
    terminal_log(
        TerminalLogLevel::Info,
        format!(
            "daemon starting terminal_backend={:?} loglevel={:?}",
            terminal_backend, config.terminal.loglevel
        ),
    );
    let sock_path = daemon_socket_path()?;
    let pid_path = daemon_pid_path()?;
    let hash_path = daemon_hash_path()?;

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
    std::fs::write(&hash_path, current_exe_hash()?).context("writing daemon hash file")?;

    let listener = UnixListener::bind(&sock_path).context("binding Unix domain socket")?;

    let (pty_tx, mut pty_rx) = mpsc::channel::<PtyEvent>(1024);

    let mut agents: HashMap<String, AgentSlot> = HashMap::new();
    let mut client: Option<tokio::net::UnixStream> = None;
    let mut subscriptions: HashSet<String> = HashSet::new();
    let mut heartbeat_interval = tokio::time::interval(Duration::from_secs(30));
    #[allow(unused_mut)]
    let mut profiler = RenderProfiler::from_env();

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
                // Drain a bounded batch of pending PTY events and coalesce
                // output per agent. Bounded to keep the select loop responsive
                // to client messages (subscribe, input) between batches.
                let mut pending = vec![evt];
                for _ in 0..31 {
                    match pty_rx.try_recv() {
                        Ok(more) => pending.push(more),
                        Err(_) => break,
                    }
                }

                let mut coalesced: HashMap<String, Vec<u8>> = HashMap::new();
                let mut exited: Vec<String> = Vec::new();

                let prof_t0 = profiler.as_ref().map(|_| Instant::now());
                for evt in pending {
                    match evt {
                        PtyEvent::RawData { id, data } => {
                            if let Some(slot) = agents.get_mut(&id) {
                                slot.process_raw_data(&data);
                            }
                            if subscriptions.contains(&id) {
                                coalesced.entry(id).or_default().extend_from_slice(&data);
                            }
                        }
                        PtyEvent::Exited { id } => {
                            if let Some(slot) = agents.get_mut(&id) {
                                slot.alive = false;
                            }
                            exited.push(id);
                        }
                    }
                }
                if let (Some(ref mut prof), Some(t0)) = (&mut profiler, prof_t0) {
                    prof.record(Stage::Parse, t0.elapsed());
                    prof.maybe_flush();
                }

                let mut disconnect = false;
                for (id, data) in coalesced {
                    if let Some(ref mut stream) = client {
                        let msg = DaemonMessage::Output { id, data };
                        if !send_to_client(stream, &msg).await {
                            disconnect = true;
                            break;
                        }
                    }
                }
                for id in exited {
                    if let Some(ref mut stream) = client {
                        let msg = DaemonMessage::Exited { id };
                        if !send_to_client(stream, &msg).await {
                            disconnect = true;
                            break;
                        }
                    }
                }
                if disconnect {
                    client = None;
                    subscriptions.clear();
                }
            }

            result = client_read => {
                match result {
                    Ok(msg) => {
                        let stream = client.as_mut().unwrap();
                        match handle_client_message(
                            msg,
                            &mut agents,
                            &mut subscriptions,
                            stream,
                            &pty_tx,
                            terminal_backend,
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
    let _ = std::fs::remove_file(&hash_path);

    Ok(())
}

enum HandleResult {
    Continue,
    Shutdown,
}

fn set_single_subscription(subscriptions: &mut HashSet<String>, id: String) {
    subscriptions.clear();
    subscriptions.insert(id);
}

#[cfg(test)]
mod subscription_tests {
    use super::*;

    #[test]
    fn setting_subscription_replaces_previous_target() {
        let mut subscriptions = HashSet::from(["old-agent".to_string()]);
        set_single_subscription(&mut subscriptions, "target-agent".to_string());
        assert_eq!(subscriptions, HashSet::from(["target-agent".to_string()]));
    }
}

async fn handle_client_message(
    msg: ClientMessage,
    agents: &mut HashMap<String, AgentSlot>,
    subscriptions: &mut HashSet<String>,
    stream: &mut tokio::net::UnixStream,
    pty_tx: &mpsc::Sender<PtyEvent>,
    terminal_backend: TerminalBackend,
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
            match spawn_agent_pty(&id, &cwd, &cmd, &env, rows, cols, pty_tx, terminal_backend) {
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
                // Output already accepted into the ring buffer belongs to the
                // old terminal geometry. Parse it before changing the model's
                // size so relative cursor movement keeps its original meaning.
                slot.sync_terminal();
                let size = PtySize {
                    rows,
                    cols,
                    pixel_width: 0,
                    pixel_height: 0,
                };
                let _ = slot.master.resize(size);
                slot.terminal.resize(rows, cols);
                terminal_log(
                    TerminalLogLevel::Info,
                    format!("daemon resize id={id} rows={rows} cols={cols}"),
                );
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
            if let Some(slot) = agents.get_mut(&id) {
                let catch_up_data = slot.catch_up_data();
                terminal_log(
                    TerminalLogLevel::Info,
                    format!(
                        "daemon subscribe id={id} catch_up_bytes={}",
                        catch_up_data.len()
                    ),
                );
                set_single_subscription(subscriptions, id.clone());
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::CatchUp {
                        id,
                        data: catch_up_data,
                        terminal_backend: slot.terminal.backend(),
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
        ClientMessage::RefreshParser { id } => {
            if let Some(slot) = agents.get_mut(&id) {
                slot.rebuild_parser();
                let catch_up_data = slot.catch_up_data();
                terminal_log(
                    TerminalLogLevel::Info,
                    format!(
                        "daemon refresh-parser id={id} catch_up_bytes={}",
                        catch_up_data.len()
                    ),
                );
                set_single_subscription(subscriptions, id.clone());
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::CatchUp {
                        id,
                        data: catch_up_data,
                        terminal_backend: slot.terminal.backend(),
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
        ClientMessage::ToggleTerminalBackend { id } => {
            if let Some(slot) = agents.get_mut(&id) {
                slot.toggle_terminal_backend();
                let catch_up_data = slot.catch_up_data();
                terminal_log(
                    TerminalLogLevel::Info,
                    format!(
                        "daemon toggle-terminal-backend id={id} backend={:?} catch_up_bytes={}",
                        slot.terminal.backend(),
                        catch_up_data.len()
                    ),
                );
                subscriptions.insert(id.clone());
                let _ = send_to_client(
                    stream,
                    &DaemonMessage::CatchUp {
                        id,
                        data: catch_up_data,
                        terminal_backend: slot.terminal.backend(),
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
                .map(|(id, slot)| {
                    let (rows, cols) = slot.terminal.size();
                    DaemonAgent {
                        id: id.clone(),
                        alive: slot.alive,
                        rows,
                        cols,
                        terminal_backend: slot.terminal.backend(),
                    }
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

#[allow(clippy::too_many_arguments)]
fn spawn_agent_pty(
    id: &str,
    cwd: &str,
    cmd: &[String],
    env: &[(String, String)],
    rows: u16,
    cols: u16,
    pty_tx: &mpsc::Sender<PtyEvent>,
    terminal_backend: TerminalBackend,
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

    // Reader thread is now minimal — just reads and forwards raw bytes.
    // All processing (query detection, sync buffering, CPR handling)
    // happens daemon-side in AgentSlot::process_raw_data().
    tokio::task::spawn_blocking(move || {
        let mut buf = [0u8; 65536];
        loop {
            match reader.read(&mut buf) {
                Ok(0) | Err(_) => {
                    let _ = tx.blocking_send(PtyEvent::Exited {
                        id: agent_id.clone(),
                    });
                    break;
                }
                Ok(n) => {
                    if tx
                        .blocking_send(PtyEvent::RawData {
                            id: agent_id.clone(),
                            data: buf[..n].to_vec(),
                        })
                        .is_err()
                    {
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
        terminal: TerminalModelState::new(terminal_backend, rows, cols, DAEMON_SCROLLBACK)?,
        alive: true,
        terminal_behind: 0,
        responder: TerminalQueryResponder::new(),
        mode_tracker: TerminalModeTracker::default(),
        trace: TraceRecorder::from_env(id)?,
    })
}
