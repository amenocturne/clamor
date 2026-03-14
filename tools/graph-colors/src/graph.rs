use std::collections::{HashMap, HashSet};
use std::path::{Path, PathBuf};

use regex::Regex;
use walkdir::WalkDir;

/// Undirected graph as adjacency list.
pub type Graph = HashMap<String, HashSet<String>>;

/// Scan the vault for .md files, build an undirected wikilink graph.
/// Returns the graph and a map of note name -> file path.
pub fn build_graph(
    vault: &Path,
    excluded_folders: &HashSet<String>,
) -> anyhow::Result<(Graph, HashMap<String, PathBuf>)> {
    let notes = collect_notes(vault, excluded_folders)?;
    let note_names: HashSet<&str> = notes.keys().map(|s| s.as_str()).collect();

    let wikilink_re =
        Regex::new(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]+)?\]\]").expect("valid regex");

    let mut graph: Graph = HashMap::new();

    // Ensure every note is a node
    for name in notes.keys() {
        graph.entry(name.clone()).or_default();
    }

    for (name, path) in &notes {
        let content = match std::fs::read_to_string(path) {
            Ok(c) => c,
            Err(_) => continue,
        };

        for cap in wikilink_re.captures_iter(&content) {
            let raw_target = &cap[1];
            // Handle folder/note links — take last segment
            let target_name = raw_target.rsplit('/').next().unwrap_or(raw_target);

            if target_name == name {
                continue; // no self-loops
            }

            if !note_names.contains(target_name) {
                continue; // target must exist in vault
            }

            // Undirected: insert both directions
            graph
                .entry(name.clone())
                .or_default()
                .insert(target_name.to_string());
            graph
                .entry(target_name.to_string())
                .or_default()
                .insert(name.clone());
        }
    }

    Ok((graph, notes))
}

/// Walk the vault and collect note stem -> path, skipping .obsidian and excluded folders.
/// When duplicates exist, prefer the shorter path (closer to root).
fn collect_notes(
    vault: &Path,
    excluded_folders: &HashSet<String>,
) -> anyhow::Result<HashMap<String, PathBuf>> {
    let mut notes: HashMap<String, PathBuf> = HashMap::new();

    for entry in WalkDir::new(vault).into_iter().filter_entry(|e| {
        let file_name = e.file_name().to_string_lossy();
        if file_name == ".obsidian" {
            return false;
        }
        if e.file_type().is_dir() && excluded_folders.contains(file_name.as_ref()) {
            return false;
        }
        true
    }) {
        let entry = entry?;
        if !entry.file_type().is_file() {
            continue;
        }

        let path = entry.path();
        let ext = path.extension().and_then(|e| e.to_str());
        if ext != Some("md") {
            continue;
        }

        let stem = match path.file_stem().and_then(|s| s.to_str()) {
            Some(s) => s.to_string(),
            None => continue,
        };

        let depth = entry.depth();
        let should_insert = match notes.get(&stem) {
            Some(existing) => {
                // Prefer shorter path (fewer components = closer to root)
                let existing_depth = existing
                    .strip_prefix(vault)
                    .map(|p| p.components().count())
                    .unwrap_or(usize::MAX);
                depth < existing_depth
            }
            None => true,
        };

        if should_insert {
            notes.insert(stem, path.to_path_buf());
        }
    }

    Ok(notes)
}

/// Degree of a node.
pub fn degree(graph: &Graph, node: &str) -> usize {
    graph.get(node).map_or(0, |neighbors| neighbors.len())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn degree_of_missing_node_is_zero() {
        let graph: Graph = HashMap::new();
        assert_eq!(degree(&graph, "nonexistent"), 0);
    }

    #[test]
    fn undirected_edges() {
        let mut graph: Graph = HashMap::new();
        graph.entry("a".into()).or_default().insert("b".into());
        graph.entry("b".into()).or_default().insert("a".into());
        assert_eq!(degree(&graph, "a"), 1);
        assert_eq!(degree(&graph, "b"), 1);
    }
}
