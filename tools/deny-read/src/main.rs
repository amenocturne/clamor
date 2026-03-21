//! Enforce per-project denyRead rules from the nearest .claude/settings.json.
//!
//! Protocol:
//! - Read JSON from stdin: {"tool_name": "...", "tool_input": {...}}
//! - To ALLOW: exit 0, print nothing to stdout
//! - To DENY: exit 0, print {"hookSpecificOutput": {"permissionDecision": "deny", ...}}
//! - On any error: exit 0 silently (never crash, never block incorrectly)

mod bash;
mod fnmatch;
mod matching;
mod path;
mod settings;

use serde::Deserialize;
use serde_json::Value;
use std::collections::HashMap;
use std::env;
use std::io::{self, Read};
use std::path::{Path, PathBuf};

use bash::{check_bash_command, is_git_only_command};
use matching::{find_denied_files_in_dir, get_denied_filenames, grep_glob_excludes_denied, matches_deny};
use path::path_name;
use settings::{find_project_settings, find_project_settings_bounded, get_deny_patterns};

#[derive(Deserialize)]
struct HookInput {
    tool_name: Option<String>,
    tool_input: Option<Value>,
}

fn deny(reason: &str) {
    let out = serde_json::json!({
        "hookSpecificOutput": {
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    });
    println!("{}", out);
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;

    let data: HookInput = serde_json::from_str(&input)?;
    let tool_name = data.tool_name.as_deref().unwrap_or("");
    let tool_input = data.tool_input.unwrap_or(Value::Null);

    let mut cache: HashMap<PathBuf, Option<Value>> = HashMap::new();

    // ----- Bash -----
    if tool_name == "Bash" {
        let command = tool_input
            .get("command")
            .and_then(|v| v.as_str())
            .unwrap_or("");

        if command.is_empty() {
            return Ok(());
        }

        if is_git_only_command(command) {
            return Ok(());
        }

        let cwd = env::current_dir()?;
        for settings_file in find_project_settings_bounded(&cwd) {
            let project_root = match settings_file.parent().and_then(|p| p.parent()) {
                Some(r) => r.to_path_buf(),
                None => continue,
            };

            let contents = match std::fs::read_to_string(&settings_file) {
                Ok(c) => c,
                Err(_) => continue,
            };
            let settings: Value = match serde_json::from_str(&contents) {
                Ok(s) => s,
                Err(_) => continue,
            };

            let patterns = get_deny_patterns(&settings);
            if patterns.is_empty() {
                continue;
            }

            if let Some(matched) = check_bash_command(command, &project_root, &patterns) {
                deny(&format!(
                    "deny-read: command accesses file matching '{}' (from {})",
                    matched,
                    path_name(&project_root)
                ));
                return Ok(());
            }
        }

        return Ok(());
    }

    // ----- Grep -----
    if tool_name == "Grep" {
        let search_path = tool_input
            .get("path")
            .and_then(|v| v.as_str())
            .map(String::from)
            .unwrap_or_else(|| {
                env::current_dir()
                    .map(|p| p.display().to_string())
                    .unwrap_or_default()
            });

        let search_path_resolved = match std::fs::canonicalize(&search_path) {
            Ok(p) => p,
            Err(_) => path::normalize_path(Path::new(&search_path)),
        };

        // If Grep targets a specific file, check it directly
        if search_path_resolved.is_file() {
            if let Some((project_root, settings)) =
                find_project_settings(Path::new(&search_path), &mut cache)
            {
                let patterns = get_deny_patterns(&settings);
                if let Some(matched) = matches_deny(&search_path, &project_root, &patterns) {
                    deny(&format!(
                        "deny-read: grep target '{}' matches deny pattern '{}' (from {})",
                        Path::new(&search_path)
                            .file_name()
                            .map(|n| n.to_string_lossy().to_string())
                            .unwrap_or_default(),
                        matched,
                        path_name(&project_root)
                    ));
                }
            }
            return Ok(());
        }

        // Grep targets a directory: check if it contains denied files
        if let Some((project_root, settings)) =
            find_project_settings(Path::new(&search_path), &mut cache)
        {
            let patterns = get_deny_patterns(&settings);
            if !patterns.is_empty() {
                let search_dir_str = search_path_resolved.display().to_string();
                let denied_in_dir =
                    find_denied_files_in_dir(&search_dir_str, &project_root, &patterns);

                if !denied_in_dir.is_empty() {
                    let grep_glob = tool_input.get("glob").and_then(|v| v.as_str());
                    let grep_type = tool_input.get("type").and_then(|v| v.as_str());

                    if let Some(gg) = grep_glob {
                        let denied_names = get_denied_filenames(&project_root, &denied_in_dir);
                        if grep_glob_excludes_denied(gg, &denied_names) {
                            return Ok(());
                        }
                    }

                    if grep_type.is_some() {
                        return Ok(());
                    }

                    let denied_str = denied_in_dir.join(", ");
                    let dir_name = Path::new(&search_path)
                        .file_name()
                        .map(|n| n.to_string_lossy().to_string())
                        .unwrap_or_else(|| "project".to_string());
                    deny(&format!(
                        "deny-read: grep on '{}' would expose files matching [{}]. \
                         Use glob or type filter to exclude denied files, \
                         or target a specific non-denied file path.",
                        dir_name, denied_str
                    ));
                }
            }
        }

        return Ok(());
    }

    // ----- File-based tools: Read, Edit, Write -----
    let file_path = match tool_input.get("file_path").and_then(|v| v.as_str()) {
        Some(fp) => fp,
        None => return Ok(()),
    };

    let (project_root, settings) = match find_project_settings(Path::new(file_path), &mut cache) {
        Some(pair) => pair,
        None => return Ok(()),
    };

    let patterns = get_deny_patterns(&settings);
    if patterns.is_empty() {
        return Ok(());
    }

    if let Some(matched) = matches_deny(file_path, &project_root, &patterns) {
        deny(&format!(
            "deny-read: '{}' matches deny pattern '{}' (from {})",
            Path::new(file_path)
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default(),
            matched,
            path_name(&project_root)
        ));
    }

    Ok(())
}

fn main() {
    // Never crash, never block incorrectly. All errors → silent allow.
    let _ = run();
}
