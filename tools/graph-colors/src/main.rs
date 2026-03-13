mod anchors;
mod color;
mod graph;
mod louvain;
mod obsidian;

use std::collections::HashSet;
use std::path::{Path, PathBuf};

const MAX_CLUSTERS: usize = 50;
const DEFAULT_MIN_CLUSTER: usize = 5;

fn main() -> anyhow::Result<()> {
    let args: Vec<String> = std::env::args().skip(1).collect();

    let mut excluded: HashSet<String> = HashSet::new();
    let mut dry_run = false;
    let mut min_cluster = DEFAULT_MIN_CLUSTER;
    let mut vault_path: Option<PathBuf> = None;

    for arg in &args {
        if let Some(folders) = arg.strip_prefix("--exclude=") {
            for f in folders.split(',') {
                let f = f.trim();
                if !f.is_empty() {
                    excluded.insert(f.to_string());
                }
            }
        } else if arg == "--dry-run" {
            dry_run = true;
        } else if let Some(val) = arg.strip_prefix("--min-cluster=") {
            min_cluster = val.parse().unwrap_or(DEFAULT_MIN_CLUSTER);
        } else if arg.starts_with('-') {
            eprintln!("Unknown flag: {arg}");
            std::process::exit(1);
        } else {
            vault_path = Some(PathBuf::from(arg));
        }
    }

    let start = vault_path.unwrap_or_else(|| std::env::current_dir().expect("cannot get cwd"));
    let start = start.canonicalize().unwrap_or_else(|_| start.clone());

    let vault = find_vault_root(&start).unwrap_or_else(|| {
        eprintln!(
            "No .obsidian directory found at or above {}. Is this an Obsidian vault?",
            start.display()
        );
        std::process::exit(1);
    });

    eprintln!("Analyzing vault: {}", vault.display());
    if !excluded.is_empty() {
        let mut sorted: Vec<&str> = excluded.iter().map(|s| s.as_str()).collect();
        sorted.sort();
        eprintln!("Excluding: {}", sorted.join(", "));
    }
    eprintln!();

    let (g, _notes) = graph::build_graph(&vault, &excluded)?;

    let communities = louvain::detect_communities(&g, min_cluster);
    let communities: Vec<_> = communities.into_iter().take(MAX_CLUSTERS).collect();

    if communities.is_empty() {
        eprintln!("No clusters detected");
        return Ok(());
    }

    let colors = color::generate_colors(communities.len());

    let mut groups: Vec<obsidian::ColorGroup> = Vec::new();
    let mut labels: Vec<String> = Vec::new();
    let mut sizes: Vec<usize> = Vec::new();
    let mut anchors_list: Vec<Vec<String>> = Vec::new();

    for (i, cluster) in communities.iter().enumerate() {
        let cluster_anchors = anchors::select_anchors(&g, cluster);

        if cluster_anchors.is_empty() {
            continue;
        }

        let query = obsidian::build_query(&cluster_anchors);
        let label = obsidian::cluster_label(&g, cluster);

        groups.push(obsidian::ColorGroup {
            query,
            color: colors[i].clone(),
        });
        labels.push(label);
        sizes.push(cluster.len());
        anchors_list.push(cluster_anchors);
    }

    if dry_run {
        obsidian::print_dry_run(&groups, &labels, &sizes, &anchors_list);
        // Also print the raw JSON for the colorGroups array
        println!("---\nRaw colorGroups JSON:\n");
        println!("{}", serde_json::to_string_pretty(&groups)?);
    } else {
        obsidian::write_graph_json(&vault, &groups)?;
    }

    Ok(())
}

/// Walk up from `start` to find the nearest directory containing `.obsidian`.
fn find_vault_root(start: &Path) -> Option<PathBuf> {
    let mut path = start.to_path_buf();
    loop {
        if path.join(".obsidian").is_dir() {
            return Some(path);
        }
        match path.parent() {
            Some(parent) if parent != path => path = parent.to_path_buf(),
            _ => return None,
        }
    }
}
