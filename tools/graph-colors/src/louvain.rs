use std::collections::{HashMap, HashSet};

use rand::rngs::SmallRng;
use rand::seq::SliceRandom;
use rand::SeedableRng;

use crate::graph::Graph;

const SEED: u64 = 42;

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
        v.sort(); // deterministic base order
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

    let mut rng = SmallRng::seed_from_u64(SEED);

    let initial_degrees: Vec<f64> = (0..n)
        .map(|i| adj.get(&i).map_or(0.0, |nbrs| nbrs.values().sum()))
        .collect();

    // Multi-level Louvain: progressively coarsen the graph.
    // Once communities are formed at a level, they're frozen into super-nodes.
    // cumulative_mapping[original_node] = current-level super-node
    let mut cumulative_mapping: Vec<usize> = (0..n).collect();
    let mut current_adj = adj;
    let mut current_n = n;
    let mut current_degrees = initial_degrees;

    loop {
        let mut community: Vec<usize> = (0..current_n).collect();
        let improved = phase1(
            &current_adj,
            &mut community,
            &current_degrees,
            m,
            current_n,
            &mut rng,
        );

        if !improved {
            break;
        }

        let (new_adj, _new_community, new_degrees, new_n, mapping) =
            aggregate(&current_adj, &community, &current_degrees, current_n);

        if new_n == current_n {
            break;
        }

        for cm in cumulative_mapping.iter_mut() {
            *cm = mapping[*cm];
        }

        current_adj = new_adj;
        current_n = new_n;
        current_degrees = new_degrees;
    }

    // Group nodes by their final super-node
    let mut groups: HashMap<usize, Vec<String>> = HashMap::new();
    for (i, &comm) in cumulative_mapping.iter().enumerate() {
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

/// Phase 1: local moves with randomized node visit order (matching NetworkX).
/// Returns true if any improvement was made.
fn phase1(
    adj: &HashMap<usize, HashMap<usize, f64>>,
    community: &mut [usize],
    degrees: &[f64],
    m: f64,
    n: usize,
    rng: &mut SmallRng,
) -> bool {
    let mut improved = false;
    let two_m = 2.0 * m;

    // Node visit order — shuffled each pass like NetworkX
    let mut order: Vec<usize> = (0..n).collect();

    loop {
        order.shuffle(rng);
        let mut moved = false;

        for &i in &order {
            let ki = degrees[i];
            let current_comm = community[i];

            // Compute edges from i to each neighboring community (exclude self-loops:
            // self-loops represent internal community structure in aggregated graphs
            // and should not count as edges to the community for modularity gain)
            let mut comm_edges: HashMap<usize, f64> = HashMap::new();
            if let Some(neighbors) = adj.get(&i) {
                for (&j, &w) in neighbors {
                    if j == i {
                        continue;
                    }
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
fn aggregate(adj: &AdjMap, community: &[usize], degrees: &[f64], n: usize) -> AggregateResult {
    // Collect unique community IDs and assign new indices
    let mut comm_ids: Vec<usize> = community
        .iter()
        .copied()
        .collect::<HashSet<_>>()
        .into_iter()
        .collect();
    comm_ids.sort();
    let comm_to_new: HashMap<usize, usize> = comm_ids
        .iter()
        .enumerate()
        .map(|(new_idx, &old_comm)| (old_comm, new_idx))
        .collect();
    let new_n = comm_ids.len();

    // mapping[old_node] = new_node_index
    let mapping: Vec<usize> = community.iter().map(|&c| comm_to_new[&c]).collect();

    // Build new adjacency (self-loops included — they represent internal community edges
    // and are essential for correct modularity computation at higher levels)
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

    // New degrees (sum of constituent original degrees)
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
            g.entry(a.to_string()).or_default().insert(b.to_string());
            g.entry(b.to_string()).or_default().insert(a.to_string());
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

        assert_eq!(
            communities.len(),
            2,
            "Expected 2 communities, got {communities:?}"
        );
    }

    #[test]
    fn filters_small_clusters() {
        let edges = [("a", "b"), ("b", "c"), ("a", "c")];
        let graph = make_graph(&edges);
        let communities = detect_communities(&graph, 10);
        assert!(communities.is_empty());
    }

    #[test]
    fn empty_graph() {
        let graph: Graph = HashMap::new();
        let communities = detect_communities(&graph, 1);
        assert!(communities.is_empty());
    }

    // -- Known-structure graphs from the literature --

    /// Zachary's Karate Club: 34 members, split into 2 factions.
    /// Standard benchmark for community detection — expected: 2-4 communities.
    /// Edges from: W. W. Zachary, "An information flow model for conflict and fission
    /// in small groups", Journal of Anthropological Research, 1977.
    #[test]
    fn zachary_karate_club() {
        let edges = [
            ("1", "2"),
            ("1", "3"),
            ("1", "4"),
            ("1", "5"),
            ("1", "6"),
            ("1", "7"),
            ("1", "8"),
            ("1", "9"),
            ("1", "11"),
            ("1", "12"),
            ("1", "13"),
            ("1", "14"),
            ("1", "18"),
            ("1", "20"),
            ("1", "22"),
            ("1", "32"),
            ("2", "3"),
            ("2", "4"),
            ("2", "8"),
            ("2", "14"),
            ("2", "18"),
            ("2", "20"),
            ("2", "22"),
            ("2", "31"),
            ("3", "4"),
            ("3", "8"),
            ("3", "9"),
            ("3", "10"),
            ("3", "14"),
            ("3", "28"),
            ("3", "29"),
            ("3", "33"),
            ("4", "8"),
            ("4", "13"),
            ("4", "14"),
            ("5", "7"),
            ("5", "11"),
            ("6", "7"),
            ("6", "11"),
            ("6", "17"),
            ("7", "17"),
            ("9", "31"),
            ("9", "33"),
            ("9", "34"),
            ("10", "34"),
            ("14", "34"),
            ("15", "33"),
            ("15", "34"),
            ("16", "33"),
            ("16", "34"),
            ("19", "33"),
            ("19", "34"),
            ("20", "34"),
            ("21", "33"),
            ("21", "34"),
            ("23", "33"),
            ("23", "34"),
            ("24", "26"),
            ("24", "28"),
            ("24", "30"),
            ("24", "33"),
            ("24", "34"),
            ("25", "26"),
            ("25", "28"),
            ("25", "32"),
            ("26", "32"),
            ("27", "30"),
            ("27", "34"),
            ("28", "34"),
            ("29", "32"),
            ("29", "34"),
            ("30", "33"),
            ("30", "34"),
            ("31", "33"),
            ("31", "34"),
            ("32", "33"),
            ("32", "34"),
            ("33", "34"),
        ];
        let graph = make_graph(&edges);
        let communities = detect_communities(&graph, 1);

        // Known ground truth: 2 factions (Mr Hi vs Officer).
        // Louvain typically finds 2-4 communities. Must find at least 2.
        assert!(
            communities.len() >= 2 && communities.len() <= 5,
            "Karate club: expected 2-5 communities, got {} → {communities:?}",
            communities.len()
        );

        // All 34 members must be assigned
        let total: usize = communities.iter().map(|c| c.len()).sum();
        assert_eq!(total, 34, "All 34 members must be assigned");
    }

    /// Four cliques of 5 nodes each, connected in a ring by single bridge edges.
    /// Clear community structure — must detect exactly 4 communities.
    #[test]
    fn four_cliques_ring() {
        let mut edges: Vec<(&str, &str)> = Vec::new();

        // Clique A: a0-a4 (fully connected)
        let a = ["a0", "a1", "a2", "a3", "a4"];
        for i in 0..5 {
            for j in (i + 1)..5 {
                edges.push((a[i], a[j]));
            }
        }
        // Clique B
        let b = ["b0", "b1", "b2", "b3", "b4"];
        for i in 0..5 {
            for j in (i + 1)..5 {
                edges.push((b[i], b[j]));
            }
        }
        // Clique C
        let c = ["c0", "c1", "c2", "c3", "c4"];
        for i in 0..5 {
            for j in (i + 1)..5 {
                edges.push((c[i], c[j]));
            }
        }
        // Clique D
        let d = ["d0", "d1", "d2", "d3", "d4"];
        for i in 0..5 {
            for j in (i + 1)..5 {
                edges.push((d[i], d[j]));
            }
        }

        // Ring bridges: A-B, B-C, C-D, D-A
        edges.push(("a4", "b0"));
        edges.push(("b4", "c0"));
        edges.push(("c4", "d0"));
        edges.push(("d4", "a0"));

        let graph = make_graph(&edges);
        let communities = detect_communities(&graph, 1);

        assert_eq!(
            communities.len(),
            4,
            "Four cliques ring: expected 4 communities, got {} → {communities:?}",
            communities.len()
        );
        for c in &communities {
            assert_eq!(
                c.len(),
                5,
                "Each clique should have 5 nodes, got {}",
                c.len()
            );
        }
    }

    /// Barbell graph: two cliques of 10 connected by a single path of 3 nodes.
    /// Should detect 2 main communities (path nodes join one side or the other).
    #[test]
    fn barbell_graph() {
        let mut edges: Vec<(String, String)> = Vec::new();

        // Left clique: L0-L9
        for i in 0..10 {
            for j in (i + 1)..10 {
                edges.push((format!("L{i}"), format!("L{j}")));
            }
        }
        // Right clique: R0-R9
        for i in 0..10 {
            for j in (i + 1)..10 {
                edges.push((format!("R{i}"), format!("R{j}")));
            }
        }
        // Bridge path: L9 - P0 - P1 - P2 - R0
        edges.push(("L9".into(), "P0".into()));
        edges.push(("P0".into(), "P1".into()));
        edges.push(("P1".into(), "P2".into()));
        edges.push(("P2".into(), "R0".into()));

        let edge_refs: Vec<(&str, &str)> = edges
            .iter()
            .map(|(a, b)| (a.as_str(), b.as_str()))
            .collect();
        let graph = make_graph(&edge_refs);
        let communities = detect_communities(&graph, 1);

        // Should detect 2 main communities (bridge nodes absorbed into one side)
        assert!(
            communities.len() >= 2 && communities.len() <= 4,
            "Barbell: expected 2-4 communities, got {} → {communities:?}",
            communities.len()
        );

        let total: usize = communities.iter().map(|c| c.len()).sum();
        assert_eq!(total, 23, "All 23 nodes must be assigned");
    }

    /// Disconnected components should become separate communities.
    #[test]
    fn disconnected_components() {
        let edges = [
            // Triangle 1
            ("x1", "x2"),
            ("x2", "x3"),
            ("x1", "x3"),
            // Triangle 2 (disconnected)
            ("y1", "y2"),
            ("y2", "y3"),
            ("y1", "y3"),
            // Triangle 3 (disconnected)
            ("z1", "z2"),
            ("z2", "z3"),
            ("z1", "z3"),
        ];
        let graph = make_graph(&edges);
        let communities = detect_communities(&graph, 1);

        assert_eq!(
            communities.len(),
            3,
            "Disconnected components: expected 3 communities, got {communities:?}"
        );
    }

    /// Star graph: one hub connected to many leaves.
    /// All nodes should be in a single community.
    #[test]
    fn star_graph_single_community() {
        let mut edges = Vec::new();
        for i in 0..20 {
            edges.push((
                "hub",
                Box::leak(format!("leaf{i}").into_boxed_str()) as &str,
            ));
        }
        let edge_refs: Vec<(&str, &str)> = edges.iter().map(|&(a, b)| (a, b)).collect();
        let graph = make_graph(&edge_refs);
        let communities = detect_communities(&graph, 1);

        assert_eq!(
            communities.len(),
            1,
            "Star graph: expected 1 community, got {communities:?}"
        );
    }
}
