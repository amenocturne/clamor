use std::path::{Path, PathBuf};

/// Find all git repositories under `root`, skipping hidden directories and nested repos.
pub fn find_git_repos(root: &Path) -> Vec<PathBuf> {
    let mut repos = Vec::new();
    scan_dir(root, false, &mut repos);
    repos.sort();
    repos
}

fn scan_dir(path: &Path, inside_repo: bool, repos: &mut Vec<PathBuf>) {
    if !path.is_dir() {
        return;
    }

    let is_repo = path.join(".git").exists();

    if is_repo && !inside_repo {
        repos.push(path.to_path_buf());
        return;
    }

    let entries = match std::fs::read_dir(path) {
        Ok(entries) => entries,
        Err(_) => return,
    };

    let mut children: Vec<PathBuf> = entries
        .filter_map(|e| e.ok())
        .map(|e| e.path())
        .filter(|p| {
            p.is_dir()
                && p.file_name()
                    .and_then(|n| n.to_str())
                    .map(|n| !n.starts_with('.'))
                    .unwrap_or(false)
        })
        .collect();

    children.sort();

    for child in children {
        scan_dir(&child, inside_repo || is_repo, repos);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn finds_repos_and_skips_hidden() {
        let tmp = std::env::temp_dir().join("gw_test_scan");
        let _ = fs::remove_dir_all(&tmp);

        // Create structure:
        // tmp/
        //   project-a/.git/
        //   project-b/.git/
        //   .hidden/.git/        <- should be skipped
        //   plain-dir/
        //     nested/.git/

        for dir in &[
            "project-a/.git",
            "project-b/.git",
            ".hidden/.git",
            "plain-dir/nested/.git",
        ] {
            fs::create_dir_all(tmp.join(dir)).unwrap();
        }

        let repos = find_git_repos(&tmp);
        let names: Vec<&str> = repos
            .iter()
            .map(|p| p.file_name().unwrap().to_str().unwrap())
            .collect();

        assert!(names.contains(&"project-a"));
        assert!(names.contains(&"project-b"));
        assert!(names.contains(&"nested"));
        assert!(!names.contains(&".hidden"));

        let _ = fs::remove_dir_all(&tmp);
    }

    #[test]
    fn skips_nested_repos() {
        let tmp = std::env::temp_dir().join("gw_test_nested");
        let _ = fs::remove_dir_all(&tmp);

        // Create repo with nested repo inside
        fs::create_dir_all(tmp.join("parent/.git")).unwrap();
        fs::create_dir_all(tmp.join("parent/child/.git")).unwrap();

        let repos = find_git_repos(&tmp);

        // Should only find parent, not child
        assert_eq!(repos.len(), 1);
        assert_eq!(repos[0].file_name().unwrap().to_str().unwrap(), "parent");

        let _ = fs::remove_dir_all(&tmp);
    }
}
