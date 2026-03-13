use std::env;
use std::path::{Component, Path, PathBuf};

/// Resolve a deny pattern to an absolute path/glob string.
pub fn resolve_pattern(pattern: &str, project_root: &Path) -> String {
    if pattern.starts_with("//") {
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

/// Normalize a path without requiring it to exist (no symlink resolution).
/// Handles `.` and `..` components and makes relative paths absolute.
pub fn normalize_path(path: &Path) -> PathBuf {
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
            Component::ParentDir => {
                components.pop();
            }
            Component::CurDir => {}
            c => components.push(c),
        }
    }

    components.iter().collect()
}

/// Get the final component (directory name) of a path, or fallback to
/// the full display string.
pub fn path_name(path: &Path) -> String {
    path.file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| path.display().to_string())
}

/// Compute a relative path from `base` to `target`, if possible.
pub fn pathdiff_relative(target: &Path, base: &Path) -> Option<String> {
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resolve_pattern() {
        let root = Path::new("/project");
        assert_eq!(resolve_pattern(".env", root), "/project/.env");
        assert_eq!(resolve_pattern("/secrets/**", root), "/project/secrets/**");
        assert_eq!(resolve_pattern("//etc/passwd", root), "/etc/passwd");
    }

    #[test]
    fn test_normalize_path() {
        let p = normalize_path(Path::new("/a/b/../c"));
        assert_eq!(p, PathBuf::from("/a/c"));

        let p = normalize_path(Path::new("/a/./b/c"));
        assert_eq!(p, PathBuf::from("/a/b/c"));
    }
}
