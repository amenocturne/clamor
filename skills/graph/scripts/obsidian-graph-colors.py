#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["networkx"]
# ///
"""
Generate and update Obsidian graph color groups based on detected clusters.

Usage:
    obsidian-graph-colors.py [--exclude=FOLDERS] [--dry-run] [--min-cluster=N]

Options:
    --exclude=FOLDERS   Comma-separated folder names to exclude (e.g., logs,tmp,archive)
    --dry-run           Print the generated groups without updating graph.json
    --min-cluster=N     Minimum cluster size to include (default: 5)

This script:
1. Detects clusters using Louvain community detection
2. For each cluster, identifies anchor notes (most connected within cluster)
3. Generates Obsidian graph queries using line:([[anchor]]) syntax
4. Updates .obsidian/graph.json with the new color groups
"""

import json
import re
import sys
from pathlib import Path

import networkx as nx

# Catppuccin Mocha palette - cohesive colors for dark themes
COLORS = [
    {"a": 1, "rgb": 9024762},  # Blue #89B4FA
    {"a": 1, "rgb": 13346551},  # Mauve #CBA6F7
    {"a": 1, "rgb": 16429959},  # Peach #FAB387
    {"a": 1, "rgb": 10937249},  # Green #A6E3A1
    {"a": 1, "rgb": 9757397},  # Teal #94E2D5
    {"a": 1, "rgb": 15442092},  # Maroon #EBA0AC
    {"a": 1, "rgb": 16376495},  # Yellow #F9E2AF
    {"a": 1, "rgb": 7653356},  # Sapphire #74C7EC
    {"a": 1, "rgb": 16106215},  # Pink #F5C2E7
    {"a": 1, "rgb": 11845374},  # Lavender #B4BEFE
]

# Match [[target]] or [[target|display]] etc.
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]+)?\]\]")

EXCLUDED_FOLDERS: set[str] = set()


def is_excluded(path: Path) -> bool:
    return any(part in EXCLUDED_FOLDERS for part in path.parts)


def find_vault_root(start: Path) -> Path:
    current = start.resolve()
    while current != current.parent:
        if (current / ".obsidian").exists():
            return current
        current = current.parent
    return start.resolve()


def get_all_notes(vault: Path) -> dict[str, Path]:
    notes = {}
    for md in vault.rglob("*.md"):
        if ".obsidian" in md.parts:
            continue
        rel_path = md.relative_to(vault)
        if is_excluded(rel_path):
            continue
        name = md.stem
        if name not in notes or len(md.parts) < len(notes[name].parts):
            notes[name] = md
    return notes


def extract_links(file: Path) -> list[str]:
    content = file.read_text()
    return WIKILINK_PATTERN.findall(content)


def build_graph(vault: Path) -> tuple[nx.Graph, dict[str, Path]]:
    notes = get_all_notes(vault)
    G = nx.Graph()

    for name in notes:
        G.add_node(name)

    for name, note_path in notes.items():
        links = extract_links(note_path)
        for target in links:
            target_name = target.split("/")[-1] if "/" in target else target
            if target_name in notes and target_name != name:
                G.add_edge(name, target_name)

    return G, notes


def detect_clusters(G: nx.Graph, min_size: int = 5) -> list[set[str]]:
    """Detect clusters using Louvain, filter by size."""
    G_connected = G.subgraph([n for n in G.nodes() if G.degree(n) > 0]).copy()

    if len(G_connected) < 3:
        return []

    try:
        communities = nx.community.louvain_communities(G_connected, seed=42)
    except AttributeError:
        communities = list(nx.community.greedy_modularity_communities(G_connected))

    # Filter by size and sort by size descending
    communities = [c for c in communities if len(c) >= min_size]
    communities = sorted(communities, key=len, reverse=True)

    return communities


def get_cluster_anchors(
    G: nx.Graph, cluster: set[str], notes: dict[str, Path], max_anchors: int = 5
) -> list[str]:
    """
    Get anchor notes for a cluster - notes that are:
    1. Well-connected within the cluster
    2. Not MOCs or index notes
    3. Representative of the cluster's content
    """
    subgraph = G.subgraph(cluster)

    # Filter out MOCs and index notes
    def is_content_note(name: str) -> bool:
        lower = name.lower()
        return not (
            lower.startswith("moc-")
            or lower.startswith("_")
            or lower.endswith("-index")
            or lower == "index"
        )

    content_nodes = [n for n in cluster if is_content_note(n)]

    if not content_nodes:
        # Fallback to all nodes if no content nodes
        content_nodes = list(cluster)

    # Sort by degree within cluster (most connected first)
    sorted_nodes = sorted(content_nodes, key=lambda n: subgraph.degree(n), reverse=True)

    return sorted_nodes[:max_anchors]


def get_cluster_label(G: nx.Graph, cluster: set[str]) -> str:
    """Get a label for the cluster based on its hub/most connected node."""
    subgraph = G.subgraph(cluster)
    hub = max(cluster, key=lambda n: subgraph.degree(n))

    # Clean up the hub name for display
    label = hub.replace("-", " ").replace("_", " ")
    # Capitalize first letter of each word
    label = " ".join(word.capitalize() for word in label.split())

    return label


def generate_query(anchors: list[str]) -> str:
    """Generate Obsidian graph query from anchor notes."""
    # Use line:("[[note]]") syntax to match notes that link to anchors
    # Brackets must be quoted as they are reserved search characters
    parts = [f'line:("[[{anchor}]]")' for anchor in anchors]
    return " OR ".join(parts)


def generate_color_groups(
    vault: Path, min_cluster_size: int = 5, max_clusters: int = 10
) -> list[dict]:
    """Generate Obsidian color groups from detected clusters."""
    G, notes = build_graph(vault)
    clusters = detect_clusters(G, min_cluster_size)

    color_groups = []

    for i, cluster in enumerate(clusters[:max_clusters]):
        anchors = get_cluster_anchors(G, cluster, notes)

        if not anchors:
            continue

        query = generate_query(anchors)
        color = COLORS[i % len(COLORS)]
        label = get_cluster_label(G, cluster)

        color_groups.append(
            {
                "query": query,
                "color": color,
                "_label": label,  # Not used by Obsidian, but helpful for debugging
                "_size": len(cluster),
                "_anchors": anchors,
            }
        )

    return color_groups


def update_graph_json(
    vault: Path, color_groups: list[dict], dry_run: bool = False
) -> bool:
    """Update .obsidian/graph.json with new color groups."""
    graph_json_path = vault / ".obsidian" / "graph.json"

    # Clean color groups for Obsidian (remove internal keys)
    clean_groups = []
    for group in color_groups:
        clean_groups.append(
            {
                "query": group["query"],
                "color": group["color"],
            }
        )

    if dry_run:
        print("Generated color groups:\n")
        for group in color_groups:
            print(f"Cluster: {group['_label']} ({group['_size']} notes)")
            print(f"  Anchors: {', '.join(group['_anchors'])}")
            print(f"  Query: {group['query'][:80]}...")
            print()
        return True

    # Read existing settings or create default
    if graph_json_path.exists():
        try:
            settings = json.loads(graph_json_path.read_text())
        except json.JSONDecodeError:
            settings = {}
    else:
        settings = {}

    # Update color groups
    settings["colorGroups"] = clean_groups

    # Write back
    graph_json_path.parent.mkdir(parents=True, exist_ok=True)
    graph_json_path.write_text(json.dumps(settings, indent=2))

    print(
        f"Updated {graph_json_path.relative_to(vault)} with {len(clean_groups)} color groups"
    )
    return True


def main():
    global EXCLUDED_FOLDERS

    args = sys.argv[1:]
    dry_run = False
    min_cluster = 5

    # Parse arguments
    remaining_args = []
    for arg in args:
        if arg.startswith("--exclude="):
            folders = arg.split("=", 1)[1]
            EXCLUDED_FOLDERS = {f.strip() for f in folders.split(",") if f.strip()}
        elif arg == "--dry-run":
            dry_run = True
        elif arg.startswith("--min-cluster="):
            min_cluster = int(arg.split("=", 1)[1])
        else:
            remaining_args.append(arg)

    vault = find_vault_root(Path.cwd())

    print(f"Analyzing vault: {vault}")
    if EXCLUDED_FOLDERS:
        print(f"Excluding: {', '.join(EXCLUDED_FOLDERS)}")
    print()

    color_groups = generate_color_groups(vault, min_cluster_size=min_cluster)

    if not color_groups:
        print("No clusters detected")
        return

    update_graph_json(vault, color_groups, dry_run=dry_run)


if __name__ == "__main__":
    main()
