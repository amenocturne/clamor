use std::path::Path;

use serde_json::Value;

use crate::color::ColorValue;

/// Build an Obsidian search query from anchor note names.
/// Uses `line:("[[Anchor]]")` syntax to match notes linking to anchors.
pub fn build_query(anchors: &[String]) -> String {
    anchors
        .iter()
        .map(|a| format!("line:(\"[[{a}]]\")"))
        .collect::<Vec<_>>()
        .join(" OR ")
}

/// A single color group entry for Obsidian's graph.json.
#[derive(Debug, serde::Serialize)]
pub struct ColorGroup {
    pub query: String,
    pub color: ColorValue,
}

/// Read existing graph.json, merge in new colorGroups, write back.
pub fn write_graph_json(
    vault: &Path,
    groups: &[ColorGroup],
) -> anyhow::Result<()> {
    let graph_json_path = vault.join(".obsidian").join("graph.json");

    let mut settings: Value = if graph_json_path.exists() {
        let content = std::fs::read_to_string(&graph_json_path)?;
        serde_json::from_str(&content).unwrap_or(Value::Object(serde_json::Map::new()))
    } else {
        Value::Object(serde_json::Map::new())
    };

    let groups_value = serde_json::to_value(groups)?;
    settings
        .as_object_mut()
        .expect("graph.json should be an object")
        .insert("colorGroups".to_string(), groups_value);

    if let Some(parent) = graph_json_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&graph_json_path, serde_json::to_string_pretty(&settings)?)?;

    let relative = graph_json_path
        .strip_prefix(vault)
        .unwrap_or(&graph_json_path);
    eprintln!(
        "Updated {} with {} color groups",
        relative.display(),
        groups.len()
    );

    Ok(())
}

/// Print color groups with debug info to stdout (dry-run mode).
pub fn print_dry_run(
    groups: &[ColorGroup],
    labels: &[String],
    sizes: &[usize],
    anchors_list: &[Vec<String>],
) {
    println!("Generated color groups:\n");
    for (i, group) in groups.iter().enumerate() {
        println!("Cluster: {} ({} notes)", labels[i], sizes[i]);
        println!("  Anchors: {}", anchors_list[i].join(", "));
        let query_preview: String = group.query.chars().take(80).collect();
        println!("  Query: {query_preview}...");
        println!();
    }
}

/// Derive a human-readable label from the cluster's most connected node.
pub fn cluster_label(graph: &crate::graph::Graph, cluster: &[String]) -> String {
    let hub = cluster
        .iter()
        .max_by_key(|n| crate::graph::degree(graph, n))
        .map(|s| s.as_str())
        .unwrap_or("unknown");

    hub.replace(['-', '_'], " ")
        .split_whitespace()
        .map(|word| {
            let mut chars = word.chars();
            match chars.next() {
                Some(c) => {
                    let upper: String = c.to_uppercase().collect();
                    format!("{upper}{}", chars.as_str())
                }
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}
