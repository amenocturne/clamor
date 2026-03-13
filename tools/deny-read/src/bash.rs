use std::env;
use std::path::Path;

use crate::path::{pathdiff_relative, resolve_pattern};

/// Check if every sub-command in a shell chain is a git operation.
pub fn is_git_only_command(command: &str) -> bool {
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
pub fn split_shell_commands(command: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut current = String::new();
    let chars: Vec<char> = command.chars().collect();
    let len = chars.len();
    let mut i = 0;
    let mut in_single_quote = false;
    let mut in_double_quote = false;

    while i < len {
        let ch = chars[i];

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

        if !in_single_quote && !in_double_quote {
            if i + 1 < len
                && ((ch == '&' && chars[i + 1] == '&') || (ch == '|' && chars[i + 1] == '|'))
            {
                parts.push(current.clone());
                current.clear();
                i += 2;
                continue;
            }
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
pub fn check_bash_command(
    command: &str,
    project_root: &Path,
    patterns: &[String],
) -> Option<String> {
    let cwd = env::current_dir().ok();

    for pattern in patterns {
        let abs_path = resolve_pattern(pattern, project_root);

        // For glob patterns like "secrets/**", also check the directory prefix
        if pattern.contains("**") {
            let dir_prefix = pattern.split("**").next().unwrap_or("");
            let abs_dir_prefix = resolve_pattern(dir_prefix, project_root);

            let cwd_rel = cwd
                .as_ref()
                .and_then(|cwd_path| pathdiff_relative(Path::new(&abs_dir_prefix), cwd_path));

            for c in [
                Some(abs_dir_prefix.as_str()),
                Some(dir_prefix),
                cwd_rel.as_deref(),
            ]
            .into_iter()
            .flatten()
            {
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

        for c in [Some(abs_path.as_str()), Some(rel_path), cwd_rel.as_deref()]
            .into_iter()
            .flatten()
        {
            if !c.is_empty() && command.contains(c) {
                return Some(pattern.clone());
            }
        }
    }

    None
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
