use serde_json::Value;
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};

use crate::path::normalize_path;

const MAX_PROJECT_DEPTH: usize = 3;

/// Walk up from `file_path` to find nearest `.claude/settings.json`.
/// Returns (project_root, settings_value) or None.
pub fn find_project_settings(
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
pub fn get_deny_patterns(settings: &Value) -> Vec<String> {
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

/// Find .claude/settings.json files up to MAX_PROJECT_DEPTH levels deep from root.
pub fn find_project_settings_bounded(root: &Path) -> Vec<PathBuf> {
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
