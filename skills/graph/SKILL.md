---
name: graph
description: Analyze Obsidian vault link graph
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

# Find notes that bridge different topic clusters
uv run scripts/wikilinks.py bridges

# Discover potential links between related notes
uv run scripts/wikilinks.py suggest 10

# Find path between two concepts
uv run scripts/wikilinks.py path "attention" "productivity"

# Safe rename with automatic backlink updates
uv run scripts/wikilinks.py rename knowledge/old-name.md knowledge/new-name.md
```
