use std::collections::HashSet;

use crate::graph::Graph;

const MAX_ANCHORS_PER_CLUSTER: usize = 15;

/// Select anchor notes for a cluster using greedy set cover.
/// Each anchor covers its neighbors within the cluster.
/// Returns up to MAX_ANCHORS_PER_CLUSTER anchors.
pub fn select_anchors(graph: &Graph, cluster: &[String]) -> Vec<String> {
    let cluster_set: HashSet<&str> = cluster.iter().map(|s| s.as_str()).collect();

    // Build coverage map: candidate -> set of cluster members it covers (neighbors in cluster)
    let coverage: Vec<(&str, HashSet<&str>)> = cluster
        .iter()
        .map(|node| {
            let neighbors = graph
                .get(node.as_str())
                .map(|nbrs| {
                    nbrs.iter()
                        .filter(|n| cluster_set.contains(n.as_str()))
                        .map(|n| n.as_str())
                        .collect()
                })
                .unwrap_or_default();
            (node.as_str(), neighbors)
        })
        .collect();

    let mut anchors: Vec<String> = Vec::new();
    let mut covered: HashSet<&str> = HashSet::new();
    let mut used: HashSet<&str> = HashSet::new();

    while anchors.len() < MAX_ANCHORS_PER_CLUSTER && covered.len() < cluster.len() {
        let mut best: Option<&str> = None;
        let mut best_count = 0usize;

        for (candidate, cov) in &coverage {
            if used.contains(candidate) {
                continue;
            }
            let new_count = cov.iter().filter(|n| !covered.contains(**n)).count();
            if new_count > best_count {
                best_count = new_count;
                best = Some(candidate);
            }
        }

        match best {
            Some(anchor) if best_count > 0 => {
                let cov = &coverage.iter().find(|(c, _)| *c == anchor).unwrap().1;
                covered.extend(cov.iter());
                covered.insert(anchor);
                used.insert(anchor);
                anchors.push(anchor.to_string());
            }
            _ => break,
        }
    }

    anchors
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    #[test]
    fn hub_node_selected_first() {
        let mut graph: Graph = HashMap::new();
        // hub connects to a, b, c; leaf only connects to hub
        for leaf in &["a", "b", "c"] {
            graph
                .entry("hub".into())
                .or_default()
                .insert(leaf.to_string());
            graph
                .entry(leaf.to_string())
                .or_default()
                .insert("hub".into());
        }

        let cluster: Vec<String> = vec!["hub", "a", "b", "c"]
            .into_iter()
            .map(String::from)
            .collect();

        let anchors = select_anchors(&graph, &cluster);
        assert_eq!(anchors[0], "hub");
    }

    #[test]
    fn respects_max_anchors() {
        let mut graph: Graph = HashMap::new();
        // Create a large cluster where each node only covers itself
        let nodes: Vec<String> = (0..30).map(|i| format!("n{i}")).collect();
        // Chain: n0-n1-n2-...-n29
        for i in 0..29 {
            graph
                .entry(nodes[i].clone())
                .or_default()
                .insert(nodes[i + 1].clone());
            graph
                .entry(nodes[i + 1].clone())
                .or_default()
                .insert(nodes[i].clone());
        }

        let anchors = select_anchors(&graph, &nodes);
        assert!(anchors.len() <= 15);
    }
}
