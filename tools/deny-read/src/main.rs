//! Enforce per-project denyRead rules from the nearest .claude/settings.json.
//!
//! Walks up from the target file to find the project's settings, loads deny
//! patterns from sandbox.filesystem.denyRead, and blocks access if matched.
//! This lets deny rules live with the project and work regardless of CWD.
//!
//! Protocol:
//! - Read JSON from stdin: {"tool_name": "...", "tool_input": {...}}
//! - To ALLOW: exit 0, print nothing to stdout
//! - To BLOCK: exit 0, print {"decision": "block", "reason": "..."} to stdout
//! - On any error: exit 0 silently (never crash, never block incorrectly)

use serde::Deserialize;
use serde_json::Value;
use std::collections::HashMap;
use std::env;
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};

/// Max directory depth to search for .claude/settings.json in bounded search.
const MAX_PROJECT_DEPTH: usize = 3;

// ---------------------------------------------------------------------------
// Data types
// ---------------------------------------------------------------------------

#[derive(Deserialize)]
struct HookInput {
    tool_name: Option<String>,
    tool_input: Option<Value>,
}

// ---------------------------------------------------------------------------
// Settings discovery
// ---------------------------------------------------------------------------

/// Walk up from `file_path` to find nearest `.claude/settings.json`.
/// Returns (project_root, settings_value) or None.
fn find_project_settings(
    file_path: &Path,
    cache: &mut HashMap<PathBuf, Option<Value>>,
) -> Option<(PathBuf, Value)> {
    let resolved = match fs::canonicalize(file_path) {
        Ok(p) => p,
        Err(_) => normalize_path(file_path),
    };

    let mut search_dir = if resolved.is_dir() {
        resolved
    } else {
        match resolved.parent() {
            Some(p) => p.to_path_buf(),
            None => return None,
        }
    };

    loop {
        if let Some(cached) = cache.get(&search_dir) {
            match cached {
                Some(settings) => return Some((search_dir.clone(), settings.clone())),
                None => {
                    // Cached as "no settings here", keep walking up
                }
            }
        } else {
            let settings_file = search_dir.join(".claude").join("settings.json");
            if settings_file.is_file() {
                if let Ok(contents) = fs::read_to_string(&settings_file) {
                    if let Ok(settings) = serde_json::from_str::<Value>(&contents) {
                        cache.insert(search_dir.clone(), Some(settings.clone()));
                        return Some((search_dir, settings));
                    }
                }
            }
            cache.insert(search_dir.clone(), None);
        }

        let parent = search_dir.parent();
        match parent {
            Some(p) if p != search_dir => search_dir = p.to_path_buf(),
            _ => break,
        }
    }

    None
}

/// Extract denyRead patterns from settings JSON.
fn get_deny_patterns(settings: &Value) -> Vec<String> {
    settings
        .get("sandbox")
        .and_then(|s| s.get("filesystem"))
        .and_then(|f| f.get("denyRead"))
        .and_then(|d| d.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default()
}

// ---------------------------------------------------------------------------
// Pattern resolution
// ---------------------------------------------------------------------------

/// Resolve a deny pattern to an absolute path/glob string.
fn resolve_pattern(pattern: &str, project_root: &Path) -> String {
    if pattern.starts_with("//") {
        // Absolute path: strip leading "/"  (// -> /)
        return pattern[1..].to_string();
    }
    if let Some(rest) = pattern.strip_prefix("~/") {
        if let Ok(home) = env::var("HOME") {
            return format!("{}/{}", home, rest);
        }
        return pattern.to_string();
    }
    if pattern.starts_with('/') {
        let stripped = pattern.trim_start_matches('/');
        return format!("{}/{}", project_root.display(), stripped);
    }
    format!("{}/{}", project_root.display(), pattern)
}

// ---------------------------------------------------------------------------
// Glob / fnmatch
// ---------------------------------------------------------------------------

/// fnmatch-style matching. Supports `*`, `?`, `[...]`, and `**` for recursive.
fn fnmatch(name: &str, pattern: &str) -> bool {
    fnmatch_inner(name.as_bytes(), pattern.as_bytes())
}

fn fnmatch_inner(name: &[u8], pattern: &[u8]) -> bool {
    let mut ni = 0;
    let mut pi = 0;
    let mut star_pi = None::<usize>; // position in pattern after last '*'
    let mut star_ni = 0usize; // position in name when we hit last '*'

    while ni < name.len() {
        if pi < pattern.len() {
            // Handle ** (matches path separators too)
            if pi + 1 < pattern.len() && pattern[pi] == b'*' && pattern[pi + 1] == b'*' {
                // Consume all consecutive * characters
                let mut pp = pi;
                while pp < pattern.len() && pattern[pp] == b'*' {
                    pp += 1;
                }
                // Skip a trailing slash after ** (so a/**/b matches a/b)
                if pp < pattern.len() && pattern[pp] == b'/' {
                    pp += 1;
                }
                // If rest of pattern is empty, match everything
                if pp >= pattern.len() {
                    return true;
                }
                // Try matching rest of pattern at every position in name.
                // Also try skipping leading '/' in name to handle zero-directory case.
                for start in ni..=name.len() {
                    if fnmatch_inner(&name[start..], &pattern[pp..]) {
                        return true;
                    }
                }
                return false;
            }

            match pattern[pi] {
                b'?' => {
                    // ? matches any single char except /
                    if name[ni] != b'/' {
                        ni += 1;
                        pi += 1;
                        continue;
                    }
                }
                b'*' => {
                    // * matches any sequence of chars except /
                    star_pi = Some(pi + 1);
                    star_ni = ni;
                    pi += 1;
                    continue;
                }
                b'[' => {
                    // Character class
                    if let Some((matched, end_pi)) = match_bracket(name[ni], &pattern[pi..]) {
                        if matched {
                            ni += 1;
                            pi += end_pi;
                            continue;
                        }
                    }
                    // Bracket didn't match or was malformed
                }
                c => {
                    if c == name[ni] {
                        ni += 1;
                        pi += 1;
                        continue;
                    }
                }
            }
        }

        // Current chars don't match. Backtrack to last '*' if possible.
        if let Some(sp) = star_pi {
            // '*' doesn't match '/'
            if name[star_ni] == b'/' {
                return false;
            }
            star_ni += 1;
            ni = star_ni;
            pi = sp;
            continue;
        }

        return false;
    }

    // Remaining pattern must be all *'s (or empty)
    while pi < pattern.len() && pattern[pi] == b'*' {
        pi += 1;
    }

    pi >= pattern.len()
}

/// Match a bracket expression `[...]` against a character.
/// Returns Some((matched, bytes_consumed)) or None if malformed.
fn match_bracket(ch: u8, pattern: &[u8]) -> Option<(bool, usize)> {
    if pattern.is_empty() || pattern[0] != b'[' {
        return None;
    }
    let mut i = 1;
    let negate = if i < pattern.len() && (pattern[i] == b'!' || pattern[i] == b'^') {
        i += 1;
        true
    } else {
        false
    };

    let mut matched = false;
    let mut first = true;

    while i < pattern.len() {
        if pattern[i] == b']' && !first {
            let result = if negate { !matched } else { matched };
            return Some((result, i + 1));
        }
        first = false;

        // Range: a-z
        if i + 2 < pattern.len() && pattern[i + 1] == b'-' && pattern[i + 2] != b']' {
            let lo = pattern[i];
            let hi = pattern[i + 2];
            if ch >= lo && ch <= hi {
                matched = true;
            }
            i += 3;
        } else {
            if pattern[i] == ch {
                matched = true;
            }
            i += 1;
        }
    }

    None // Malformed: no closing ]
}

// ---------------------------------------------------------------------------
// File matching
// ---------------------------------------------------------------------------

/// Check if file_path matches any deny pattern. Returns the matched pattern or None.
fn matches_deny(file_path: &str, project_root: &Path, patterns: &[String]) -> Option<String> {
    let resolved = match fs::canonicalize(file_path) {
        Ok(p) => p.display().to_string(),
        Err(_) => normalize_path(Path::new(file_path)).display().to_string(),
    };

    for pattern in patterns {
        let abs_pattern = resolve_pattern(pattern, project_root);
        if fnmatch(&resolved, &abs_pattern) {
            return Some(pattern.clone());
        }
    }

    None
}

/// Expand deny patterns into actual filenames (just the name component) that
/// exist on disk.
fn get_denied_filenames(project_root: &Path, patterns: &[String]) -> Vec<String> {
    let mut names = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for pattern in patterns {
        let abs_pattern = resolve_pattern(pattern, project_root);
        if abs_pattern.contains('*') {
            if let Ok(entries) = glob::glob(&abs_pattern) {
                for entry in entries.flatten() {
                    if let Some(name) = entry.file_name() {
                        let n = name.to_string_lossy().to_string();
                        if seen.insert(n.clone()) {
                            names.push(n);
                        }
                    }
                }
            }
        } else if let Some(name) = Path::new(&abs_pattern).file_name() {
            let n = name.to_string_lossy().to_string();
            if seen.insert(n.clone()) {
                names.push(n);
            }
        }
    }

    names
}

/// Check if a Grep glob filter naturally excludes all denied filenames.
fn grep_glob_excludes_denied(grep_glob: &str, denied_names: &[String]) -> bool {
    for name in denied_names {
        if fnmatch(name, grep_glob) {
            return false;
        }
    }
    true
}

/// Return list of deny patterns that have matching files under search_dir.
fn find_denied_files_in_dir(
    search_dir: &str,
    project_root: &Path,
    patterns: &[String],
) -> Vec<String> {
    let resolved_dir = match fs::canonicalize(search_dir) {
        Ok(p) => p,
        Err(_) => normalize_path(Path::new(search_dir)),
    };
    let resolved_dir_str = resolved_dir.display().to_string();

    let mut matched = Vec::new();

    for pattern in patterns {
        let abs_pattern = resolve_pattern(pattern, project_root);

        if abs_pattern.contains('*') {
            if let Ok(entries) = glob::glob(&abs_pattern) {
                let mut found = false;
                for entry in entries.flatten() {
                    let canonical = match fs::canonicalize(&entry) {
                        Ok(p) => p,
                        Err(_) => continue,
                    };
                    if canonical.starts_with(&resolved_dir) {
                        found = true;
                        break;
                    }
                }
                if found {
                    matched.push(pattern.clone());
                }
            }
        } else {
            let abs_path = match fs::canonicalize(&abs_pattern) {
                Ok(p) => p.display().to_string(),
                Err(_) => normalize_path(Path::new(&abs_pattern))
                    .display()
                    .to_string(),
            };
            if abs_path.starts_with(&resolved_dir_str) {
                matched.push(pattern.clone());
            }
        }
    }

    matched
}

// ---------------------------------------------------------------------------
// Bash command handling
// ---------------------------------------------------------------------------

/// Check if every sub-command in a shell chain is a git operation.
fn is_git_only_command(command: &str) -> bool {
    let parts = split_shell_commands(command);
    for part in &parts {
        let trimmed = part.trim();
        if trimmed.is_empty() {
            continue;
        }
        let tokens: Vec<&str> = trimmed.split_whitespace().collect();
        if tokens.is_empty() {
            continue;
        }

        // Skip env-var assignments (FOO=bar) and cd
        let mut idx = 0;
        while idx < tokens.len() {
            let tok = tokens[idx];
            if tok == "cd" && idx + 1 < tokens.len() {
                idx += 2;
            } else if tok.contains('=') && !tok.starts_with('-') {
                idx += 1;
            } else {
                break;
            }
        }
        if idx >= tokens.len() {
            continue;
        }
        if tokens[idx] != "git" {
            return false;
        }
    }
    true
}

/// Split a shell command string on `&&`, `||`, `;` while respecting quoted strings.
fn split_shell_commands(command: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut current = String::new();
    let chars: Vec<char> = command.chars().collect();
    let len = chars.len();
    let mut i = 0;
    let mut in_single_quote = false;
    let mut in_double_quote = false;

    while i < len {
        let ch = chars[i];

        // Handle quotes
        if ch == '\'' && !in_double_quote {
            in_single_quote = !in_single_quote;
            current.push(ch);
            i += 1;
            continue;
        }
        if ch == '"' && !in_single_quote {
            in_double_quote = !in_double_quote;
            current.push(ch);
            i += 1;
            continue;
        }

        // Only split when not inside quotes
        if !in_single_quote && !in_double_quote {
            // Check for && or ||
            if i + 1 < len
                && ((ch == '&' && chars[i + 1] == '&') || (ch == '|' && chars[i + 1] == '|'))
            {
                parts.push(current.clone());
                current.clear();
                i += 2;
                continue;
            }
            // Check for ;
            if ch == ';' {
                parts.push(current.clone());
                current.clear();
                i += 1;
                continue;
            }
        }

        current.push(ch);
        i += 1;
    }

    if !current.is_empty() {
        parts.push(current);
    }

    parts
}

/// Check if a Bash command references denied files.
fn check_bash_command(command: &str, project_root: &Path, patterns: &[String]) -> Option<String> {
    let cwd = env::current_dir().ok();

    for pattern in patterns {
        let abs_path = resolve_pattern(pattern, project_root);

        // For glob patterns like "secrets/**", also check the directory prefix
        if pattern.contains("**") {
            let dir_prefix = pattern.split("**").next().unwrap_or("");
            let abs_dir_prefix = resolve_pattern(dir_prefix, project_root);

            let cwd_rel = cwd.as_ref().and_then(|cwd_path| {
                pathdiff_relative(Path::new(&abs_dir_prefix), cwd_path)
            });

            for c in [Some(abs_dir_prefix.as_str()), Some(dir_prefix), cwd_rel.as_deref()].into_iter().flatten() {
                if !c.is_empty() && command.contains(c) {
                    return Some(pattern.clone());
                }
            }
        }

        // Check literal matches (relative, absolute, CWD-relative)
        let rel_path = pattern.trim_start_matches('/');

        let cwd_rel = cwd
            .as_ref()
            .and_then(|cwd_path| pathdiff_relative(Path::new(&abs_path), cwd_path));

        for c in [
            Some(abs_path.as_str()),
            Some(rel_path),
            cwd_rel.as_deref(),
        ].into_iter().flatten() {
            if !c.is_empty() && command.contains(c) {
                return Some(pattern.clone());
            }
        }
    }

    None
}

/// Compute a relative path from `base` to `target`, if possible.
/// Returns the string representation.
fn pathdiff_relative(target: &Path, base: &Path) -> Option<String> {
    // Simple implementation: if target starts with base, strip base prefix
    let target_str = target.to_str()?;
    let base_str = base.to_str()?;

    if let Some(remainder) = target_str.strip_prefix(base_str) {
        let remainder = remainder.trim_start_matches('/');
        if remainder.is_empty() {
            return Some(".".to_string());
        }
        return Some(remainder.to_string());
    }

    None
}

// ---------------------------------------------------------------------------
// Bounded settings search (for Bash)
// ---------------------------------------------------------------------------

/// Find .claude/settings.json files up to MAX_PROJECT_DEPTH levels deep from root.
fn find_project_settings_bounded(root: &Path) -> Vec<PathBuf> {
    let mut results = Vec::new();

    for depth in 0..=MAX_PROJECT_DEPTH {
        let pattern = if depth == 0 {
            format!("{}/.claude/settings.json", root.display())
        } else {
            let stars = (0..depth).map(|_| "*").collect::<Vec<_>>().join("/");
            format!("{}/{}/.claude/settings.json", root.display(), stars)
        };

        if let Ok(entries) = glob::glob(&pattern) {
            for entry in entries.flatten() {
                results.push(entry);
            }
        }
    }

    results
}

// ---------------------------------------------------------------------------
// Path utilities
// ---------------------------------------------------------------------------

/// Normalize a path without requiring it to exist (no symlink resolution).
/// Handles `.` and `..` components and makes relative paths absolute.
fn normalize_path(path: &Path) -> PathBuf {
    let path = if path.is_relative() {
        if let Ok(cwd) = env::current_dir() {
            cwd.join(path)
        } else {
            path.to_path_buf()
        }
    } else {
        path.to_path_buf()
    };

    let mut components = Vec::new();
    for component in path.components() {
        match component {
            std::path::Component::ParentDir => {
                components.pop();
            }
            std::path::Component::CurDir => {}
            c => components.push(c),
        }
    }

    components.iter().collect()
}

/// Get the final component (directory name) of a path, or fallback to
/// the full display string.
fn path_name(path: &Path) -> String {
    path.file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| path.display().to_string())
}

// ---------------------------------------------------------------------------
// Output
// ---------------------------------------------------------------------------

fn block(reason: &str) {
    let out = serde_json::json!({
        "decision": "block",
        "reason": reason,
    });
    println!("{}", out);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

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

        // Git commands are safe — they don't print file contents.
        if is_git_only_command(command) {
            return Ok(());
        }

        // Bounded depth search instead of rglob
        let cwd = env::current_dir()?;
        for settings_file in find_project_settings_bounded(&cwd) {
            let project_root = match settings_file.parent().and_then(|p| p.parent()) {
                Some(r) => r.to_path_buf(),
                None => continue,
            };

            let contents = match fs::read_to_string(&settings_file) {
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
                block(&format!(
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

        let search_path_resolved = match fs::canonicalize(&search_path) {
            Ok(p) => p,
            Err(_) => normalize_path(Path::new(&search_path)),
        };

        // If Grep targets a specific file, check it directly
        if search_path_resolved.is_file() {
            if let Some((project_root, settings)) =
                find_project_settings(Path::new(&search_path), &mut cache)
            {
                let patterns = get_deny_patterns(&settings);
                if let Some(matched) = matches_deny(&search_path, &project_root, &patterns) {
                    block(&format!(
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
                        let denied_names =
                            get_denied_filenames(&project_root, &denied_in_dir);
                        if grep_glob_excludes_denied(gg, &denied_names) {
                            return Ok(());
                        }
                    }

                    if grep_type.is_some() {
                        // Typed searches target specific language files — safe.
                        return Ok(());
                    }

                    let denied_str = denied_in_dir.join(", ");
                    let dir_name = Path::new(&search_path)
                        .file_name()
                        .map(|n| n.to_string_lossy().to_string())
                        .unwrap_or_else(|| "project".to_string());
                    block(&format!(
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
        block(&format!(
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fnmatch_basic() {
        assert!(fnmatch("foo.txt", "*.txt"));
        assert!(fnmatch("foo.txt", "foo.*"));
        assert!(fnmatch("foo.txt", "foo.txt"));
        assert!(!fnmatch("foo.txt", "bar.txt"));
        assert!(!fnmatch("foo.txt", "*.rs"));
    }

    #[test]
    fn test_fnmatch_star_no_slash() {
        // Single * should NOT match path separators
        assert!(!fnmatch("dir/foo.txt", "*.txt"));
        assert!(fnmatch("dir/foo.txt", "dir/*.txt"));
    }

    #[test]
    fn test_fnmatch_doublestar() {
        assert!(fnmatch("a/b/c/foo.txt", "a/**/foo.txt"));
        assert!(fnmatch("a/foo.txt", "a/**/foo.txt"));
        assert!(fnmatch("secrets/deep/nested/key.pem", "secrets/**"));
        assert!(fnmatch("/project/secrets/key.pem", "/project/secrets/**"));
    }

    #[test]
    fn test_fnmatch_question_mark() {
        assert!(fnmatch("foo.txt", "fo?.txt"));
        assert!(!fnmatch("fooo.txt", "fo?.txt"));
    }

    #[test]
    fn test_fnmatch_bracket() {
        assert!(fnmatch("foo.txt", "foo.[tx][xo][ta]"));
        assert!(fnmatch("a", "[abc]"));
        assert!(!fnmatch("d", "[abc]"));
        assert!(fnmatch("d", "[!abc]"));
    }

    #[test]
    fn test_is_git_only_command() {
        assert!(is_git_only_command("git status"));
        assert!(is_git_only_command("git add . && git commit -m 'test'"));
        assert!(is_git_only_command("cd foo && git log"));
        assert!(is_git_only_command("GIT_DIR=/tmp git status"));
        assert!(!is_git_only_command("cat .env"));
        assert!(!is_git_only_command("git status && cat .env"));
        assert!(!is_git_only_command("echo hello"));
    }

    #[test]
    fn test_split_shell_commands() {
        let parts = split_shell_commands("git add . && git commit -m 'msg'");
        assert_eq!(parts.len(), 2);
        assert_eq!(parts[0].trim(), "git add .");
        assert_eq!(parts[1].trim(), "git commit -m 'msg'");

        // Semicolons inside quotes should not split
        let parts = split_shell_commands("echo 'hello; world' && git status");
        assert_eq!(parts.len(), 2);
        assert!(parts[0].contains("hello; world"));
    }

    #[test]
    fn test_resolve_pattern() {
        let root = Path::new("/project");
        assert_eq!(resolve_pattern(".env", root), "/project/.env");
        assert_eq!(resolve_pattern("/secrets/**", root), "/project/secrets/**");
        assert_eq!(resolve_pattern("//etc/passwd", root), "/etc/passwd");
    }

    #[test]
    fn test_grep_glob_excludes_denied() {
        let denied = vec![".env".to_string(), "secrets.yml".to_string()];
        // "*.rs" should exclude both .env and secrets.yml
        assert!(grep_glob_excludes_denied("*.rs", &denied));
        // "*.yml" would match secrets.yml
        assert!(!grep_glob_excludes_denied("*.yml", &denied));
    }

    #[test]
    fn test_normalize_path() {
        let p = normalize_path(Path::new("/a/b/../c"));
        assert_eq!(p, PathBuf::from("/a/c"));

        let p = normalize_path(Path::new("/a/./b/c"));
        assert_eq!(p, PathBuf::from("/a/b/c"));
    }
}
