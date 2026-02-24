---
name: graph
description: Obsidian vault graph analysis. Use when user wants to analyze note connections, find orphans, or understand vault structure. Produces insights about link patterns and note relationships.
author: amenocturne
---

# Graph Analysis

Analyze the wikilink structure of an Obsidian vault using NetworkX.

> All script paths below are relative to this skill folder.

## Usage

Run from anywhere inside the vault:

```bash
uv run scripts/wikilinks.py [--exclude=FOLDERS] <command> [args]
```

### Global Options

| Option | Description |
|--------|-------------|
| `--exclude=FOLDERS` | Comma-separated folder names to exclude from analysis |

## Commands

### Basic Link Analysis

| Command | Description |
|---------|-------------|
| `links <file>` | Show outgoing links from a file |
| `backlinks <file>` | Show files that link to a file |
| `orphans` | Show files with no incoming links |
| `broken` | Show broken links (targets that don't exist) |
| `stats` | Show vault graph statistics |

### Graph Intelligence

| Command | Description |
|---------|-------------|
| `popular [--alpha]` | Notes with unusually high incoming links |
| `hubs [--alpha]` | Notes with unusually high outgoing links |
| `ghosts [--alpha]` | Missing notes referenced unusually often |
| `bridges [N]` | Notes that connect different clusters (high betweenness) |
| `meta-ideas [N]` | Content notes bridging multiple domains (participation coefficient) |
| `weak` | Fragile notes with only 1 connection |

### Discovery

| Command | Description |
|---------|-------------|
| `suggest [N]` | Suggest missing links (notes with shared neighbors) |
| `clusters` | Detect communities/clusters using Louvain algorithm |
| `path <note1> <note2>` | Find shortest path between two notes |

### Refactoring

| Command | Description |
|---------|-------------|
| `rename <old> <new>` | Rename file and update all references |

## Options

- `--alpha`: Sort results alphabetically instead of by count
- `N`: Number of results (default: 20 for bridges/suggest)

## Examples

```bash
# Analyze vault excluding non-knowledge folders
uv run scripts/wikilinks.py --exclude=logs,tmp,archive stats

# Find orphan notes that need more connections
uv run scripts/wikilinks.py orphans

# See which concepts are most referenced
uv run scripts/wikilinks.py popular

# Find notes that bridge different topic clusters (includes MOCs)
uv run scripts/wikilinks.py bridges

# Find meta-ideas: content notes that connect multiple domains (excludes MOCs)
uv run scripts/wikilinks.py meta-ideas

# Discover potential links between related notes
uv run scripts/wikilinks.py suggest 10

# Find path between two concepts
uv run scripts/wikilinks.py path "attention" "productivity"

# Safe rename with automatic backlink updates
uv run scripts/wikilinks.py rename knowledge/old-name.md knowledge/new-name.md
```

## Obsidian Graph Colors

Auto-generate Obsidian graph color groups based on detected clusters.

```bash
uv run scripts/obsidian-graph-colors.py [--exclude=FOLDERS] [--dry-run] [--min-cluster=N]
```

### Options

| Option | Description |
|--------|-------------|
| `--exclude=FOLDERS` | Comma-separated folder names to exclude |
| `--dry-run` | Preview groups without updating graph.json |
| `--min-cluster=N` | Minimum cluster size to include (default: 5) |

### How It Works

1. Detects clusters using Louvain community detection
2. For each cluster, identifies "anchor" notes (most connected content notes)
3. Generates Obsidian queries: `line:([[anchor1]]) OR line:([[anchor2]]) ...`
4. Updates `.obsidian/graph.json` with color groups

### Examples

```bash
# Preview what groups would be generated
uv run scripts/obsidian-graph-colors.py --exclude=logs,tmp,archive --dry-run

# Update graph.json with cluster-based colors
uv run scripts/obsidian-graph-colors.py --exclude=logs,tmp,archive

# Only include larger clusters (10+ notes)
uv run scripts/obsidian-graph-colors.py --exclude=logs,tmp,archive --min-cluster=10
```

### Automation

Use the `graph-colors` hook to auto-update on conversation end:

```yaml
# In manifest.yaml
hooks:
  - graph-colors
```
