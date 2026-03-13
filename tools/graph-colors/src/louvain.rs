use std::collections::{HashMap, HashSet};

use crate::graph::Graph;

/// Run Louvain community detection on the graph.
/// Returns communities as Vec<Vec<String>>, sorted by size descending.
/// Only returns communities with at least `min_size` members.
pub fn detect_communities(graph: &Graph, min_size: usize) -> Vec<Vec<String>> {
    // Work only with connected nodes (degree > 0)
    let connected: Vec<String> = {
        let mut v: Vec<String> = graph
            .iter()
            .filter(|(_, neighbors)| !neighbors.is_empty())
            .map(|(name, _)| name.clone())
            .collect();
        v.sort(); // deterministic order
        v
    };

    if connected.len() < 3 {
        return Vec::new();
    }

    // Build a working adjacency list with only connected nodes
    let node_set: HashSet<&str> = connected.iter().map(|s| s.as_str()).collect();
    let mut adj: HashMap<usize, HashMap<usize, f64>> = HashMap::new();
    let node_to_idx: HashMap<&str, usize> = connected
        .iter()
        .enumerate()
        .map(|(i, n)| (n.as_str(), i))
        .collect();
    let n = connected.len();

    let mut total_edges: f64 = 0.0;

    for (i, name) in connected.iter().enumerate() {
        if let Some(neighbors) = graph.get(name) {
            for neighbor in neighbors {
                if node_set.contains(neighbor.as_str()) {
                    let j = node_to_idx[neighbor.as_str()];
                    if i < j {
                        total_edges += 1.0;
                    }
                    adj.entry(i).or_default().insert(j, 1.0);
                }
            }
        }
    }

    let m = total_edges; // total edge weight

    if m == 0.0 {
        return Vec::new();
    }

    // Phase 1 initial assignment: each node in its own community
    let mut community: Vec<usize> = (0..n).collect();
    let degrees: Vec<f64> = (0..n)
        .map(|i| adj.get(&i).map_or(0.0, |nbrs| nbrs.values().sum()))
        .collect();

    loop {
        let improved = phase1(&adj, &mut community, &degrees, m, n);
        if !improved {
            break;
        }

        // Phase 2: aggregate into super-nodes
        let (new_adj, new_community, new_degrees, new_n, mapping) =
            aggregate(&adj, &community, &degrees, n);

        if new_n == n {
            break; // no reduction
        }

        // Update community assignments back to original nodes
        // mapping[old_idx] = new_idx in aggregated graph
        // new_community[new_idx] = community in aggregated graph
        // We need to track original node -> final community
        // For simplicity, we track through the mapping

        // Replace working state with aggregated graph
        let _old_n = n;
        let n_inner = new_n;
        let adj_inner = new_adj;
        let degrees_inner = new_degrees;
        let mut community_inner = new_community;

        // Run phase 1 on aggregated graph
        let improved2 = phase1(&adj_inner, &mut community_inner, &degrees_inner, m, n_inner);

        // Map back: for each original node, find its final community
        for c in community.iter_mut() {
            let super_node = mapping[*c];
            *c = community_inner[super_node];
        }

        if !improved2 {
            break;
        }
    }

    // Group nodes by community
    let mut groups: HashMap<usize, Vec<String>> = HashMap::new();
    for (i, &comm) in community.iter().enumerate() {
        groups.entry(comm).or_default().push(connected[i].clone());
    }

    let mut communities: Vec<Vec<String>> = groups
        .into_values()
        .filter(|g| g.len() >= min_size)
        .collect();

    // Sort by size descending, then alphabetically by first member for stability
    communities.sort_by(|a, b| {
        b.len()
            .cmp(&a.len())
            .then_with(|| a.first().cmp(&b.first()))
    });

    // Sort members within each community for determinism
    for comm in &mut communities {
        comm.sort();
    }

    communities
}

/// Phase 1: local moves. Returns true if any improvement was made.
fn phase1(
    adj: &HashMap<usize, HashMap<usize, f64>>,
    community: &mut [usize],
    degrees: &[f64],
    m: f64,
    n: usize,
) -> bool {
    let mut improved = false;
    let two_m = 2.0 * m;

    loop {
        let mut moved = false;

        for i in 0..n {
            let ki = degrees[i];
            let current_comm = community[i];

            // Compute edges from i to each neighboring community
            let mut comm_edges: HashMap<usize, f64> = HashMap::new();
            if let Some(neighbors) = adj.get(&i) {
                for (&j, &w) in neighbors {
                    let cj = community[j];
                    *comm_edges.entry(cj).or_default() += w;
                }
            }

            // Compute sigma_tot for each candidate community (sum of degrees)
            // and k_i_in (edges from i to that community)
            let mut best_comm = current_comm;
            let mut best_gain = 0.0_f64;

            // Sigma_tot for current community (excluding i)
            let sigma_tot_current: f64 = (0..n)
                .filter(|&j| j != i && community[j] == current_comm)
                .map(|j| degrees[j])
                .sum();
            let k_i_in_current = comm_edges.get(&current_comm).copied().unwrap_or(0.0);

            // Cost of removing i from current community
            let remove_cost = k_i_in_current / m - ki * sigma_tot_current / (two_m * m);

            // Try each neighboring community
            let candidate_comms: HashSet<usize> = comm_edges.keys().copied().collect();
            for &target_comm in &candidate_comms {
                if target_comm == current_comm {
                    continue;
                }

                let sigma_tot_target: f64 = (0..n)
                    .filter(|&j| community[j] == target_comm)
                    .map(|j| degrees[j])
                    .sum();
                let k_i_in_target = comm_edges.get(&target_comm).copied().unwrap_or(0.0);

                // Gain of adding i to target community
                let add_gain = k_i_in_target / m - ki * sigma_tot_target / (two_m * m);

                let delta_q = add_gain - remove_cost;
                if delta_q > best_gain {
                    best_gain = delta_q;
                    best_comm = target_comm;
                }
            }

            if best_comm != current_comm {
                community[i] = best_comm;
                moved = true;
                improved = true;
            }
        }

        if !moved {
            break;
        }
    }

    improved
}

type AdjMap = HashMap<usize, HashMap<usize, f64>>;

/// Result of aggregating communities into super-nodes:
/// (adjacency, community assignment, degrees, node count, old→new mapping)
type AggregateResult = (AdjMap, Vec<usize>, Vec<f64>, usize, Vec<usize>);

/// Phase 2: aggregate communities into super-nodes.
fn aggregate(
    adj: &AdjMap,
    community: &[usize],
    degrees: &[f64],
    n: usize,
) -> AggregateResult {
    // Collect unique community IDs and assign new indices
    let mut comm_ids: Vec<usize> = community.iter().copied().collect::<HashSet<_>>().into_iter().collect();
    comm_ids.sort();
    let comm_to_new: HashMap<usize, usize> = comm_ids
        .iter()
        .enumerate()
        .map(|(new_idx, &old_comm)| (old_comm, new_idx))
        .collect();
    let new_n = comm_ids.len();

    // mapping[old_node] = new_node_index
    let mapping: Vec<usize> = community
        .iter()
        .map(|&c| comm_to_new[&c])
        .collect();

    // Build new adjacency
    let mut new_adj: HashMap<usize, HashMap<usize, f64>> = HashMap::new();
    for i in 0..n {
        let ci = mapping[i];
        if let Some(neighbors) = adj.get(&i) {
            for (&j, &w) in neighbors {
                let cj = mapping[j];
                *new_adj.entry(ci).or_default().entry(cj).or_default() += w;
            }
        }
    }

    // Remove self-loops from adjacency for community detection purposes
    // (self-loops represent internal edges — they don't affect modularity optimization)
    for (&node, neighbors) in new_adj.iter_mut() {
        neighbors.remove(&node);
    }

    // New degrees (sum of edge weights including self-loops counted in original)
    let mut new_degrees = vec![0.0_f64; new_n];
    for (i, &d) in degrees.iter().enumerate() {
        new_degrees[mapping[i]] += d;
    }

    // Each new node starts in its own community
    let new_community: Vec<usize> = (0..new_n).collect();

    (new_adj, new_community, new_degrees, new_n, mapping)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_graph(edges: &[(&str, &str)]) -> Graph {
        let mut g: Graph = HashMap::new();
        for (a, b) in edges {
            g.entry(a.to_string())
                .or_default()
                .insert(b.to_string());
            g.entry(b.to_string())
                .or_default()
                .insert(a.to_string());
        }
        g
    }

    #[test]
    fn two_cliques_detected() {
        // Two triangles connected by a single bridge
        let edges = [
            ("a1", "a2"),
            ("a2", "a3"),
            ("a1", "a3"),
            ("b1", "b2"),
            ("b2", "b3"),
            ("b1", "b3"),
            ("a3", "b1"), // bridge
        ];
        let graph = make_graph(&edges);
        let communities = detect_communities(&graph, 2);

        // Should detect 2 communities
        assert_eq!(communities.len(), 2, "Expected 2 communities, got {communities:?}");
    }

    #[test]
    fn filters_small_clusters() {
        let edges = [("a", "b"), ("b", "c"), ("a", "c")];
        let graph = make_graph(&edges);
        // min_size 10 should filter out the single 3-node cluster
        let communities = detect_communities(&graph, 10);
        assert!(communities.is_empty());
    }

    #[test]
    fn empty_graph() {
        let graph: Graph = HashMap::new();
        let communities = detect_communities(&graph, 1);
        assert!(communities.is_empty());
    }
}
