use std::collections::HashSet;
use std::fs;
use std::path::Path;

use crate::fnmatch::fnmatch;
use crate::path::{normalize_path, resolve_pattern};

/// Check if file_path matches any deny pattern. Returns the matched pattern or None.
pub fn matches_deny(file_path: &str, project_root: &Path, patterns: &[String]) -> Option<String> {
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
pub fn get_denied_filenames(project_root: &Path, patterns: &[String]) -> Vec<String> {
    let mut names = Vec::new();
    let mut seen = HashSet::new();

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
pub fn grep_glob_excludes_denied(grep_glob: &str, denied_names: &[String]) -> bool {
    for name in denied_names {
        if fnmatch(name, grep_glob) {
            return false;
        }
    }
    true
}

/// Return list of deny patterns that have matching files under search_dir.
pub fn find_denied_files_in_dir(
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_grep_glob_excludes_denied() {
        let denied = vec![".env".to_string(), "secrets.yml".to_string()];
        assert!(grep_glob_excludes_denied("*.rs", &denied));
        assert!(!grep_glob_excludes_denied("*.yml", &denied));
    }
}
