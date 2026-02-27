#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["networkx"]
# ///
"""
Wikilink management for Obsidian vaults.

Usage:
    wikilinks.py [--exclude=FOLDERS] <command> [args]

Global options:
    --exclude=FOLDERS   Comma-separated folder names to exclude (e.g., --exclude=logs,tmp,templates)

Commands:
    links <file>          Show outgoing links from a file
    backlinks <file>      Show files that link to a file
    rename <old> <new>    Rename file and update all references
    orphans               Show files with no incoming links
    broken                Show broken links
    stats                 Show vault graph statistics
    popular [--alpha]     Show notes with unusually high incoming links
    hubs [--alpha]        Show notes with unusually high outgoing links
    ghosts [--alpha]      Show missing notes referenced unusually often
    bridges [N]           Show notes that connect different clusters
    meta-ideas [N]        Show content notes bridging multiple domains
    suggest [N]           Suggest missing links (notes with shared neighbors)
    clusters [--no-moc]   Show detected communities/clusters
    path <note1> <note2>  Find shortest path between two notes
    weak                  Show fragile notes (only 1 connection)
"""

import re
import sys
from collections import defaultdict
from math import sqrt
from pathlib import Path

import networkx as nx

# Match [[target]] or [[target|display]] or [[target#heading]] etc.
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]+)?\]\]")

# Global excluded folders (set by main via --exclude)
EXCLUDED_FOLDERS: set[str] = set()


def is_excluded(path: Path) -> bool:
    """Check if path is in an excluded folder."""
    return any(part in EXCLUDED_FOLDERS for part in path.parts)


def find_vault_root(start: Path) -> Path:
    """Find vault root by looking for .obsidian folder."""
    current = start.resolve()
    while current != current.parent:
        if (current / ".obsidian").exists():
            return current
        current = current.parent
    return start.resolve()


def get_all_notes(vault: Path) -> dict[str, Path]:
    """Map note names (without extension) to their paths."""
    notes = {}
    for md in vault.rglob("*.md"):
        if ".obsidian" in md.parts:
            continue
        rel_path = md.relative_to(vault)
        if is_excluded(rel_path):
            continue
        name = md.stem
        # If duplicate names, prefer shorter path
        if name not in notes or len(md.parts) < len(notes[name].parts):
            notes[name] = md
    return notes


def calc_stats(values: list[int]) -> tuple[float, float]:
    """Calculate mean and standard deviation."""
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    variance = sum((x - mean) ** 2 for x in values) / n
    return mean, sqrt(variance)


def find_outliers(
    counts: dict[str, int], multiplier: float = 1.5
) -> tuple[list[tuple[str, int]], int, float]:
    """
    Find items with counts above mean + multiplier * std.
    Returns (outliers sorted by count desc, threshold, mean).
    """
    if not counts:
        return [], 0, 0.0

    values = list(counts.values())
    mean, std = calc_stats(values)
    threshold = int(mean + multiplier * std)

    # Ensure threshold is at least 1 to avoid showing everything
    threshold = max(threshold, 1)

    outliers = [(name, count) for name, count in counts.items() if count > threshold]
    outliers.sort(key=lambda x: (-x[1], x[0]))  # Sort by count desc, then name

    return outliers, threshold, mean


def extract_links(file: Path) -> list[str]:
    """Extract all wikilink targets from a file."""
    content = file.read_text()
    return WIKILINK_PATTERN.findall(content)


def resolve_link(target: str, notes: dict[str, Path], vault: Path) -> Path | None:
    """Resolve a wikilink target to a file path."""
    # Handle path-style links like [[folder/note]]
    if "/" in target:
        path = vault / f"{target}.md"
        if path.exists():
            return path
        # Try just the filename part
        target = target.split("/")[-1]

    return notes.get(target)


def cmd_links(file: Path, vault: Path):
    """Show outgoing links from a file."""
    if not file.exists():
        print(f"File not found: {file}", file=sys.stderr)
        sys.exit(1)

    notes = get_all_notes(vault)
    links = extract_links(file)

    if not links:
        print("No outgoing links")
        return

    seen = set()
    for target in links:
        if target in seen:
            continue
        seen.add(target)

        resolved = resolve_link(target, notes, vault)
        if resolved:
            rel = resolved.relative_to(vault)
            print(f"  {target} -> {rel}")
        else:
            print(f"  {target} -> (broken)")


def cmd_backlinks(file: Path, vault: Path):
    """Show files that link to a file."""
    if not file.exists():
        print(f"File not found: {file}", file=sys.stderr)
        sys.exit(1)

    target_name = file.stem
    notes = get_all_notes(vault)
    backlinks = []

    for note_path in notes.values():
        if note_path == file:
            continue
        links = extract_links(note_path)
        for link in links:
            # Normalize link for comparison
            link_name = link.split("/")[-1] if "/" in link else link
            if link_name == target_name:
                backlinks.append(note_path)
                break

    if not backlinks:
        print("No backlinks")
        return

    for bl in sorted(backlinks):
        print(f"  {bl.relative_to(vault)}")


def cmd_rename(old: Path, new: Path, vault: Path):
    """Rename file and update all references."""
    if not old.exists():
        print(f"File not found: {old}", file=sys.stderr)
        sys.exit(1)

    if new.exists():
        print(f"Target already exists: {new}", file=sys.stderr)
        sys.exit(1)

    old_name = old.stem
    new_name = new.stem
    notes = get_all_notes(vault)

    # Find and update all files that link to old
    updated = []
    for note_path in notes.values():
        content = note_path.read_text()

        # Pattern to match links to old file
        # Handles [[old]], [[old|text]], [[old#heading]], [[path/old]], etc.
        pattern = re.compile(
            r"\[\[([^\]|#]*?/?)" + re.escape(old_name) + r"(#[^\]|]*)?(\|[^\]]+)?\]\]"
        )

        new_content = pattern.sub(
            lambda m: f"[[{m.group(1)}{new_name}{m.group(2) or ''}{m.group(3) or ''}]]",
            content,
        )

        if new_content != content:
            note_path.write_text(new_content)
            updated.append(note_path)

    # Rename the file
    new.parent.mkdir(parents=True, exist_ok=True)
    old.rename(new)

    print(f"Renamed: {old.relative_to(vault)} -> {new.relative_to(vault)}")
    if updated:
        print(f"Updated {len(updated)} file(s):")
        for f in updated:
            print(f"  {f.relative_to(vault)}")


def cmd_orphans(vault: Path):
    """Show files with no incoming links."""
    notes = get_all_notes(vault)

    # Count incoming links for each note
    incoming = {name: 0 for name in notes}

    for note_path in notes.values():
        links = extract_links(note_path)
        for target in links:
            target_name = target.split("/")[-1] if "/" in target else target
            if target_name in incoming:
                incoming[target_name] += 1

    orphans = [name for name, count in incoming.items() if count == 0]

    if not orphans:
        print("No orphans")
        return

    for name in sorted(orphans):
        print(f"  {notes[name].relative_to(vault)}")


def cmd_broken(vault: Path):
    """Show broken links."""
    notes = get_all_notes(vault)
    broken = []

    for note_path in notes.values():
        links = extract_links(note_path)
        for target in links:
            if not resolve_link(target, notes, vault):
                broken.append((note_path, target))

    if not broken:
        print("No broken links")
        return

    for file, target in broken:
        print(f"  {file.relative_to(vault)}: [[{target}]]")


def build_graph(
    vault: Path,
) -> tuple[dict[str, Path], dict[str, int], dict[str, int], dict[str, int]]:
    """
    Build the full link graph.
    Returns (notes, incoming_counts, outgoing_counts, ghost_counts).
    """
    notes = get_all_notes(vault)

    incoming = {name: 0 for name in notes}
    outgoing = {name: 0 for name in notes}
    ghosts: dict[str, int] = {}  # Non-existent notes -> reference count

    for name, note_path in notes.items():
        links = extract_links(note_path)
        unique_targets = set()

        for target in links:
            target_name = target.split("/")[-1] if "/" in target else target
            unique_targets.add(target_name)

        outgoing[name] = len(unique_targets)

        for target_name in unique_targets:
            if target_name in incoming:
                incoming[target_name] += 1
            else:
                # Ghost note (doesn't exist)
                ghosts[target_name] = ghosts.get(target_name, 0) + 1

    return notes, incoming, outgoing, ghosts


def build_nx_graph(vault: Path) -> tuple[nx.Graph, dict[str, Path]]:
    """
    Build a NetworkX graph from the vault.
    Returns undirected graph (for connectivity analysis) and notes dict.
    """
    notes = get_all_notes(vault)
    G = nx.Graph()

    # Add all notes as nodes
    for name in notes:
        G.add_node(name)

    # Add edges
    for name, note_path in notes.items():
        links = extract_links(note_path)
        for target in links:
            target_name = target.split("/")[-1] if "/" in target else target
            if target_name in notes and target_name != name:
                G.add_edge(name, target_name)

    return G, notes


def build_nx_digraph(vault: Path) -> tuple[nx.DiGraph, dict[str, Path]]:
    """
    Build a directed NetworkX graph from the vault.
    Returns directed graph and notes dict.
    """
    notes = get_all_notes(vault)
    G = nx.DiGraph()

    # Add all notes as nodes
    for name in notes:
        G.add_node(name)

    # Add edges (directed: from source to target)
    for name, note_path in notes.items():
        links = extract_links(note_path)
        seen = set()
        for target in links:
            target_name = target.split("/")[-1] if "/" in target else target
            if target_name in notes and target_name != name and target_name not in seen:
                G.add_edge(name, target_name)
                seen.add(target_name)

    return G, notes


def cmd_stats(vault: Path):
    """Show vault graph statistics."""
    notes, incoming, outgoing, ghosts = build_graph(vault)

    total_notes = len(notes)
    total_links = sum(outgoing.values())
    total_ghosts = len(ghosts)
    total_ghost_refs = sum(ghosts.values())

    # Count orphans and broken
    orphan_count = sum(1 for c in incoming.values() if c == 0)

    in_mean, in_std = calc_stats(list(incoming.values()))
    out_mean, out_std = calc_stats(list(outgoing.values()))

    print(f"Notes:          {total_notes}")
    print(f"Total links:    {total_links}")
    print(f"Ghost notes:    {total_ghosts} ({total_ghost_refs} references)")
    print(f"Orphans:        {orphan_count}")
    print("")
    print(f"Incoming links: {in_mean:.1f} avg, {in_std:.1f} std")
    print(f"Outgoing links: {out_mean:.1f} avg, {out_std:.1f} std")


def cmd_popular(vault: Path, sort_alpha: bool = False):
    """Show notes with unusually high incoming links."""
    notes, incoming, _, _ = build_graph(vault)

    outliers, threshold, mean = find_outliers(incoming)

    if not outliers:
        print(f"No popular notes (threshold: >{threshold} incoming, avg: {mean:.1f})")
        return

    if sort_alpha:
        outliers.sort(key=lambda x: x[0])

    print(f"Popular notes (>{threshold} incoming links, avg: {mean:.1f}):")
    for name, count in outliers:
        rel_path = str(notes[name].relative_to(vault))
        print(f"  {rel_path:<45} {count}")


def cmd_hubs(vault: Path, sort_alpha: bool = False):
    """Show notes with unusually high outgoing links."""
    notes, _, outgoing, _ = build_graph(vault)

    outliers, threshold, mean = find_outliers(outgoing)

    if not outliers:
        print(f"No hub notes (threshold: >{threshold} outgoing, avg: {mean:.1f})")
        return

    if sort_alpha:
        outliers.sort(key=lambda x: x[0])

    print(f"Hub notes (>{threshold} outgoing links, avg: {mean:.1f}):")
    for name, count in outliers:
        rel_path = str(notes[name].relative_to(vault))
        print(f"  {rel_path:<45} {count}")


def cmd_ghosts(vault: Path, sort_alpha: bool = False):
    """Show non-existent notes referenced unusually often."""
    _, _, _, ghosts = build_graph(vault)

    outliers, threshold, mean = find_outliers(ghosts)

    if not outliers:
        print(
            f"No notable ghosts (threshold: >{threshold} references, avg: {mean:.1f})"
        )
        return

    if sort_alpha:
        outliers.sort(key=lambda x: x[0])

    print(f"Ghost notes (>{threshold} references, avg: {mean:.1f}):")
    for name, count in outliers:
        display = f"[[{name}]]"
        print(f"  {display:<45} {count}")


def cmd_bridges(vault: Path, top_n: int = 20):
    """Show notes with highest betweenness centrality (bridge nodes)."""
    G, notes = build_nx_graph(vault)

    # Calculate betweenness centrality
    centrality = nx.betweenness_centrality(G)

    # Sort by centrality descending
    sorted_nodes = sorted(centrality.items(), key=lambda x: -x[1])

    # Filter out zero centrality and take top N
    bridges = [(name, score) for name, score in sorted_nodes if score > 0][:top_n]

    if not bridges:
        print("No bridge notes found")
        return

    print("Bridge notes (high betweenness centrality):")
    print("These notes connect different parts of the knowledge graph.\n")
    for name, score in bridges:
        rel_path = str(notes[name].relative_to(vault))
        print(f"  {rel_path:<50} {score:.4f}")


def cmd_suggest(vault: Path, top_n: int = 20):
    """Suggest missing links based on common neighbors."""
    G, notes = build_nx_graph(vault)

    # Find pairs with many common neighbors but no direct link
    suggestions: dict[tuple[str, str], int] = {}

    for node in G.nodes():
        neighbors = set(G.neighbors(node))
        if len(neighbors) < 2:
            continue

        # For each pair of neighbors, they share this node as common neighbor
        neighbors_list = list(neighbors)
        for i, n1 in enumerate(neighbors_list):
            for n2 in neighbors_list[i + 1 :]:
                # Skip if already connected
                if G.has_edge(n1, n2):
                    continue
                pair = tuple(sorted([n1, n2]))
                suggestions[pair] = suggestions.get(pair, 0) + 1

    if not suggestions:
        print("No link suggestions found")
        return

    # Sort by number of common neighbors
    sorted_suggestions = sorted(suggestions.items(), key=lambda x: -x[1])[:top_n]

    print("Conceptually close notes (many shared neighbors, no direct link):")
    print("Review if a meaningful connection exists.\n")
    for (n1, n2), common_count in sorted_suggestions:
        print(f"  [[{n1}]] <-> [[{n2}]]")
        print(f"      {common_count} shared neighbors\n")


def cmd_clusters(vault: Path, exclude_mocs: bool = False):
    """Detect and show communities in the graph."""
    G, notes = build_nx_graph(vault)

    # Optionally remove MOC nodes to see organic clustering
    if exclude_mocs:
        moc_nodes = [n for n in G.nodes() if n.lower().startswith("moc-")]
        G = G.copy()
        G.remove_nodes_from(moc_nodes)
        print(f"(Excluded {len(moc_nodes)} MOC nodes)\n")

    # Remove isolated nodes for better clustering
    G_connected = G.subgraph([n for n in G.nodes() if G.degree(n) > 0]).copy()

    if len(G_connected) == 0:
        print("No connected notes to cluster")
        return

    # Use Louvain community detection
    try:
        communities = nx.community.louvain_communities(G_connected, seed=42)
    except AttributeError:
        # Fallback for older networkx versions
        communities = list(nx.community.greedy_modularity_communities(G_connected))

    # Sort communities by size
    communities = sorted(communities, key=len, reverse=True)

    print(f"Detected {len(communities)} clusters:\n")

    for i, community in enumerate(communities[:10]):  # Show top 10 clusters
        # Find the most connected node in this community (likely the topic)
        subgraph = G_connected.subgraph(community)
        hub = max(community, key=lambda n: subgraph.degree(n))

        print(f"Cluster {i + 1}: {len(community)} notes")
        print(f"  Hub: [[{hub}]]")

        # Show a few representative notes
        sample = sorted(community, key=lambda n: -subgraph.degree(n))[:5]
        for name in sample:
            if name != hub:
                print(f"    - [[{name}]]")
        print()

    # Summary of smaller clusters
    if len(communities) > 10:
        remaining = sum(len(c) for c in communities[10:])
        print(f"  ... and {len(communities) - 10} smaller clusters ({remaining} notes)")


def cmd_path(vault: Path, note1: str, note2: str):
    """Find shortest path between two notes."""
    G, notes = build_nx_graph(vault)

    # Normalize note names (remove .md if present)
    note1 = note1.replace(".md", "")
    note2 = note2.replace(".md", "")

    # Handle partial names - find best match
    def find_note(query: str) -> str | None:
        if query in notes:
            return query
        # Try case-insensitive match
        for name in notes:
            if name.lower() == query.lower():
                return name
        # Try partial match
        matches = [name for name in notes if query.lower() in name.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            print(f"Ambiguous: '{query}' matches: {matches[:5]}")
            return None
        return None

    n1 = find_note(note1)
    n2 = find_note(note2)

    if not n1:
        print(f"Note not found: {note1}")
        return
    if not n2:
        print(f"Note not found: {note2}")
        return

    try:
        path = nx.shortest_path(G, n1, n2)
        print(f"Path from [[{n1}]] to [[{n2}]] ({len(path) - 1} hops):\n")
        for i, name in enumerate(path):
            prefix = "  " if i == 0 else "  → "
            print(f"{prefix}[[{name}]]")
    except nx.NetworkXNoPath:
        print(f"No path exists between [[{n1}]] and [[{n2}]]")
        print("These notes are in disconnected parts of the graph.")


def cmd_weak(vault: Path):
    """Show fragile notes with only 1 connection."""
    G, notes = build_nx_graph(vault)

    weak_notes = [(name, G.degree(name)) for name in G.nodes() if G.degree(name) == 1]
    weak_notes.sort(key=lambda x: x[0])

    if not weak_notes:
        print("No weak notes (all notes have 2+ connections)")
        return

    print(f"Weak notes (only 1 connection) - {len(weak_notes)} total:\n")
    for name, _ in weak_notes:
        neighbor = list(G.neighbors(name))[0]
        rel_path = str(notes[name].relative_to(vault))
        print(f"  {rel_path:<50} via [[{neighbor}]]")


def cmd_meta_ideas(vault: Path, top_n: int = 20):
    """
    Find meta-ideas: content notes that bridge multiple knowledge domains.

    Uses participation coefficient - measures how evenly a node's connections
    are distributed across different communities. High coefficient means
    the note connects multiple clusters rather than being embedded in just one.
    """
    G, notes = build_nx_graph(vault)

    # Remove isolated nodes
    G_connected = G.subgraph([n for n in G.nodes() if G.degree(n) > 0]).copy()

    if len(G_connected) < 3:
        print("Not enough connected notes to analyze")
        return

    # Detect communities
    try:
        communities = nx.community.louvain_communities(G_connected, seed=42)
    except AttributeError:
        communities = list(nx.community.greedy_modularity_communities(G_connected))

    # Build node -> community mapping
    node_to_community: dict[str, int] = {}
    for i, community in enumerate(communities):
        for node in community:
            node_to_community[node] = i

    # Calculate participation coefficient for each node
    # P_i = 1 - sum((k_is / k_i)^2) for all communities s
    # where k_is = edges from node i to community s, k_i = total degree
    participation: dict[str, float] = {}
    community_connections: dict[str, dict[int, int]] = {}  # node -> {community: count}

    for node in G_connected.nodes():
        degree = G_connected.degree(node)
        if degree < 2:  # Need at least 2 connections for meaningful participation
            continue

        # Count connections to each community
        comm_counts: dict[int, int] = defaultdict(int)
        for neighbor in G_connected.neighbors(node):
            neighbor_comm = node_to_community[neighbor]
            comm_counts[neighbor_comm] += 1

        community_connections[node] = dict(comm_counts)

        # Calculate participation coefficient
        # P = 1 - sum((k_s/k)^2)
        # P = 0 means all connections in one community
        # P approaches 1 means connections spread evenly across all communities
        sum_squared = sum((count / degree) ** 2 for count in comm_counts.values())
        p = 1 - sum_squared

        # Only include if connected to multiple communities
        if len(comm_counts) > 1:
            participation[node] = p

    if not participation:
        print("No cross-domain notes found")
        return

    # Filter out MOCs and other index-style notes
    def is_index_note(name: str) -> bool:
        lower = name.lower()
        return (
            lower.startswith("moc-")
            or lower.startswith("_")
            or lower.endswith("-index")
            or lower == "index"
        )

    # Calculate composite score: participation * (num_communities - 1)
    # This rewards both even distribution AND connecting many communities
    composite_scores = {}
    for name, p_coeff in participation.items():
        if is_index_note(name):
            continue
        num_comms = len(community_connections.get(name, {}))
        # Score = participation * community_factor
        # community_factor grows with more communities connected
        composite_scores[name] = p_coeff * (num_comms - 1)

    # Sort by composite score (descending)
    sorted_nodes = sorted(
        [(name, composite_scores[name]) for name in composite_scores],
        key=lambda x: (-x[1], x[0]),
    )[:top_n]

    if not sorted_nodes:
        print("No meta-ideas found (only MOCs bridge communities)")
        return

    print("Meta-ideas (content notes bridging multiple domains):\n")
    print(f"{'Note':<50} {'Score':<7} {'P.coef':<7} {'Clusters'}")
    print("-" * 80)

    for name, score in sorted_nodes:
        rel_path = str(notes[name].relative_to(vault))
        comm_info = community_connections.get(name, {})
        num_comms = len(comm_info)
        p_coeff = participation[name]

        # Get community hubs for context
        connected_comms = sorted(comm_info.keys(), key=lambda c: -comm_info[c])[:4]
        comm_hubs = []
        for c in connected_comms:
            # Find the hub (most connected node) of this community
            comm_nodes = list(communities[c])
            subgraph = G_connected.subgraph(comm_nodes)
            hub = max(comm_nodes, key=lambda n: subgraph.degree(n))
            comm_hubs.append(hub)

        print(f"  {rel_path:<48} {score:.2f}    {p_coeff:.2f}    {num_comms}")
        print(f"      bridges: {', '.join(f'[[{h}]]' for h in comm_hubs)}")
        print()


def main():
    global EXCLUDED_FOLDERS

    # Parse --exclude option before command
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg.startswith("--exclude="):
            folders = arg.split("=", 1)[1]
            EXCLUDED_FOLDERS = {f.strip() for f in folders.split(",") if f.strip()}
            args = args[:i] + args[i + 1 :]
            break

    if len(args) < 1:
        print(__doc__)
        sys.exit(1)

    vault = find_vault_root(Path.cwd())
    cmd = args[0]

    if cmd == "links" and len(args) >= 2:
        file = Path(args[1])
        if not file.is_absolute():
            file = vault / file
        cmd_links(file, vault)

    elif cmd == "backlinks" and len(args) >= 2:
        file = Path(args[1])
        if not file.is_absolute():
            file = vault / file
        cmd_backlinks(file, vault)

    elif cmd == "rename" and len(args) >= 3:
        old = Path(args[1])
        new = Path(args[2])
        if not old.is_absolute():
            old = vault / old
        if not new.is_absolute():
            new = vault / new
        cmd_rename(old, new, vault)

    elif cmd == "orphans":
        cmd_orphans(vault)

    elif cmd == "broken":
        cmd_broken(vault)

    elif cmd == "stats":
        cmd_stats(vault)

    elif cmd == "popular":
        sort_alpha = "--alpha" in args
        cmd_popular(vault, sort_alpha)

    elif cmd == "hubs":
        sort_alpha = "--alpha" in args
        cmd_hubs(vault, sort_alpha)

    elif cmd == "ghosts":
        sort_alpha = "--alpha" in args
        cmd_ghosts(vault, sort_alpha)

    elif cmd == "bridges":
        top_n = 20
        if len(args) >= 2 and args[1].isdigit():
            top_n = int(args[1])
        cmd_bridges(vault, top_n)

    elif cmd == "meta-ideas":
        top_n = 20
        if len(args) >= 2 and args[1].isdigit():
            top_n = int(args[1])
        cmd_meta_ideas(vault, top_n)

    elif cmd == "suggest":
        top_n = 20
        if len(args) >= 2 and args[1].isdigit():
            top_n = int(args[1])
        cmd_suggest(vault, top_n)

    elif cmd == "clusters":
        exclude_mocs = "--no-moc" in args
        cmd_clusters(vault, exclude_mocs)

    elif cmd == "path" and len(args) >= 3:
        cmd_path(vault, args[1], args[2])

    elif cmd == "weak":
        cmd_weak(vault)

    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
