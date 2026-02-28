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
import math
import re
import sys
from pathlib import Path

import networkx as nx

MAX_CLUSTERS = 50


def oklch_to_rgb(lightness: float, chroma: float, hue_deg: float) -> tuple[int, int, int]:
    """Convert OKLCH to sRGB. Returns (r, g, b) as 0-255 ints."""
    # OKLCH -> OKLAB
    hue_rad = math.radians(hue_deg)
    a = chroma * math.cos(hue_rad)
    b = chroma * math.sin(hue_rad)

    # OKLAB -> linear RGB
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b

    l = l_ ** 3
    m = m_ ** 3
    s = s_ ** 3

    r_lin = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g_lin = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    b_lin = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    # Linear RGB -> sRGB (gamma correction)
    def to_srgb(c: float) -> int:
        if c <= 0.0031308:
            c = 12.92 * c
        else:
            c = 1.055 * (c ** (1 / 2.4)) - 0.055
        return max(0, min(255, int(c * 255)))

    return to_srgb(r_lin), to_srgb(g_lin), to_srgb(b_lin)


def generate_colors(n: int) -> list[dict]:
    """Generate n perceptually uniform colors using OKLCH."""
    colors = []
    for i in range(n):
        hue = (i / n) * 360
        r, g, b = oklch_to_rgb(0.75, 0.12, hue)
        rgb_int = (r << 16) + (g << 8) + b
        colors.append({"a": 1, "rgb": rgb_int})
    return colors

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
    G: nx.Graph, cluster: set[str], notes: dict[str, Path], max_anchors: int = 15
) -> list[str]:
    """
    Select anchors using greedy set cover to maximize coverage.

    Each anchor "covers" notes that link to it. We greedily pick anchors
    that cover the most uncovered notes until we hit max_anchors or full coverage.
    """
    subgraph = G.subgraph(cluster)

    # All cluster members are candidates - MOCs and index notes often provide best coverage
    candidates = set(cluster)

    # Build coverage map: for each candidate, which notes link TO it?
    # (These are the notes that will match `line:("[[anchor]]")`)
    coverage: dict[str, set[str]] = {}
    for candidate in candidates:
        # Notes in cluster that have an edge to this candidate
        linkers = {n for n in subgraph.neighbors(candidate) if n in cluster}
        coverage[candidate] = linkers

    # Greedy set cover
    anchors = []
    covered: set[str] = set()

    while len(anchors) < max_anchors and len(covered) < len(cluster):
        # Find candidate that covers most uncovered notes
        best_anchor = None
        best_new_coverage = 0

        for candidate in candidates:
            if candidate in anchors:
                continue
            new_coverage = len(coverage[candidate] - covered)
            if new_coverage > best_new_coverage:
                best_new_coverage = new_coverage
                best_anchor = candidate

        if best_anchor is None or best_new_coverage == 0:
            break

        anchors.append(best_anchor)
        covered.update(coverage[best_anchor])
        # Also count the anchor itself as covered
        covered.add(best_anchor)

    return anchors


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


def generate_color_groups(vault: Path, min_cluster_size: int = 5) -> list[dict]:
    """Generate Obsidian color groups from detected clusters."""
    G, notes = build_graph(vault)
    clusters = detect_clusters(G, min_cluster_size)
    clusters = clusters[:MAX_CLUSTERS]

    if not clusters:
        return []

    colors = generate_colors(len(clusters))
    color_groups = []

    for i, cluster in enumerate(clusters):
        anchors = get_cluster_anchors(G, cluster, notes)

        if not anchors:
            continue

        query = generate_query(anchors)
        label = get_cluster_label(G, cluster)

        color_groups.append(
            {
                "query": query,
                "color": colors[i],
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
