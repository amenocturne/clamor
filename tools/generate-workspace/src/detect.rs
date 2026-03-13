use std::collections::BTreeSet;
use std::path::Path;
use std::process::Command;
use std::time::Duration;

/// (filename, techs, tools)
const TECH_DETECTORS: &[(&str, &[&str], &[&str])] = &[
    ("build.sbt", &["scala"], &["sbt"]),
    ("package.json", &["javascript", "typescript"], &["npm"]),
    ("Cargo.toml", &["rust"], &["cargo"]),
    ("go.mod", &["go"], &[]),
    ("pyproject.toml", &["python"], &["uv"]),
    ("build.gradle", &["kotlin", "java"], &["gradle"]),
    ("build.gradle.kts", &["kotlin", "java"], &["gradle"]),
    ("Package.swift", &["swift"], &["spm"]),
];

/// (substring pattern, techs, tools)
const TECH_PATH_PATTERNS: &[(&str, &[&str], &[&str])] = &[
    (".xcodeproj/", &["swift"], &["xcode"]),
];

/// (extensions, techs, tools)
const TECH_EXTENSIONS: &[(&[&str], &[&str], &[&str])] = &[
    (&[".yaml", ".yml"], &["yaml"], &[]),
];

const BUN_LOCK_FILES: &[&str] = &["bun.lockb", "bun.lock"];

/// Run `git ls-files` in the repo directory with a 30s timeout.
fn get_tracked_files(repo: &Path) -> Vec<String> {
    let child = Command::new("git")
        .args(["ls-files"])
        .current_dir(repo)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn();

    let mut child = match child {
        Ok(c) => c,
        Err(_) => return Vec::new(),
    };

    // Wait with timeout using a thread
    let timeout = Duration::from_secs(30);
    let start = std::time::Instant::now();

    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                if status.success() {
                    let output = child.wait_with_output().unwrap_or_else(|_| {
                        std::process::Output {
                            status,
                            stdout: Vec::new(),
                            stderr: Vec::new(),
                        }
                    });
                    return String::from_utf8_lossy(&output.stdout)
                        .lines()
                        .map(|s| s.to_string())
                        .collect();
                }
                return Vec::new();
            }
            Ok(None) => {
                if start.elapsed() > timeout {
                    let _ = child.kill();
                    return Vec::new();
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(_) => return Vec::new(),
        }
    }
}

/// Detect technologies and tools for a repo. Returns a single sorted, deduplicated list.
pub fn detect_tech_stack(repo: &Path) -> Vec<String> {
    let mut techs = BTreeSet::new();
    let mut tools = BTreeSet::new();

    let tracked_files = get_tracked_files(repo);
    let has_tracked = !tracked_files.is_empty();

    if has_tracked {
        // Exact filename matches
        for &(filename, tech_list, tool_list) in TECH_DETECTORS {
            let suffix = format!("/{}", filename);
            let found = tracked_files
                .iter()
                .any(|f| f == filename || f.ends_with(&suffix));
            if found {
                techs.extend(tech_list.iter().map(|s| s.to_string()));
                tools.extend(tool_list.iter().map(|s| s.to_string()));
            }
        }

        // Path pattern matches
        for &(pattern, tech_list, tool_list) in TECH_PATH_PATTERNS {
            let found = tracked_files.iter().any(|f| f.contains(pattern));
            if found {
                techs.extend(tech_list.iter().map(|s| s.to_string()));
                tools.extend(tool_list.iter().map(|s| s.to_string()));
            }
        }

        // Extension matches
        for &(extensions, tech_list, tool_list) in TECH_EXTENSIONS {
            let found = tracked_files
                .iter()
                .any(|f| extensions.iter().any(|ext| f.ends_with(ext)));
            if found {
                techs.extend(tech_list.iter().map(|s| s.to_string()));
                tools.extend(tool_list.iter().map(|s| s.to_string()));
            }
        }

        // Check for bun lock files -> replace npm with bun
        let has_bun = tracked_files
            .iter()
            .any(|f| BUN_LOCK_FILES.iter().any(|b| f == *b));
        if has_bun && tools.contains("npm") {
            tools.remove("npm");
            tools.insert("bun".to_string());
        }
    }

    // Fallback: check root directory directly
    if techs.is_empty() && tools.is_empty() {
        for &(filename, tech_list, tool_list) in TECH_DETECTORS {
            if repo.join(filename).exists() {
                techs.extend(tech_list.iter().map(|s| s.to_string()));
                tools.extend(tool_list.iter().map(|s| s.to_string()));
            }
        }
    }

    let mut combined: Vec<String> = techs.into_iter().chain(tools).collect();
    combined.sort();
    combined.dedup();

    if combined.is_empty() {
        vec!["unknown".to_string()]
    } else {
        combined
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_for_empty_repo() {
        let tmp = std::env::temp_dir().join("gw_test_detect_empty");
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(tmp.join(".git")).unwrap();

        // Initialize a real git repo so git ls-files works (returns empty)
        let _ = Command::new("git")
            .args(["init"])
            .current_dir(&tmp)
            .output();

        let tech = detect_tech_stack(&tmp);
        assert_eq!(tech, vec!["unknown"]);

        let _ = std::fs::remove_dir_all(&tmp);
    }

    #[test]
    fn detects_cargo_from_filesystem_fallback() {
        let tmp = std::env::temp_dir().join("gw_test_detect_cargo");
        let _ = std::fs::remove_dir_all(&tmp);
        std::fs::create_dir_all(tmp.join(".git")).unwrap();
        std::fs::write(tmp.join("Cargo.toml"), "[package]").unwrap();

        // No git init, so git ls-files will fail -> fallback to filesystem
        let tech = detect_tech_stack(&tmp);
        assert!(tech.contains(&"rust".to_string()));
        assert!(tech.contains(&"cargo".to_string()));

        let _ = std::fs::remove_dir_all(&tmp);
    }
}
