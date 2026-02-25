---
name: confluence
description: Import Confluence pages to Markdown via @acq-tech/confluence CLI. Use when user mentions Confluence import, downloading wiki pages, or converting Confluence to Markdown. Triggers on "confluence", "wiki import", "импорт страниц", "confluence to markdown".
author: amenocturne
---

# Confluence

Import Confluence pages to local Markdown files using `@acq-tech/confluence`.

## Setup

Before first use, add the internal npm registry:

```bash
npm config set registry <internal-registry-url>
```

Add Confluence credentials to `.claude/agentic-kit.json` at the workspace root:

```json
{
  "confluence": {
    "host": "https://confluence.example.com",
    "username": "yourname"
  }
}
```

Optionally generate a `.wiki.config.yml` for per-project settings (Jira hosts, retry config):

```bash
npx @acq-tech/confluence generate-config
```

## Config File (`.wiki.config.yml`)

```yaml
useBadge: false          # Use <Badge/> component in generated markdown
useJsonViewer: false     # Use JSON viewer for JSON content

jiraHosts:               # Jira hosts for link resolution
  - host: https://jira.example.com
    prefix:
      - ITAL
      - AS

timeout: 10000           # Request timeout (ms)
maxRetries: 3            # Max retry attempts
baseDelay: 1000          # Base delay for exponential backoff (ms)
```

Set all relevant Jira hosts and project prefixes for correct link imports.

## Running Import

Use the wrapper script (reads host + username from `agentic-kit.json` automatically):

```bash
uv run skills/confluence/scripts/confluence.py --page-id 123456 --folder-path ./docs
uv run skills/confluence/scripts/confluence.py --page-id 123456 --folder-path ./docs --recursive
```

Override config values ad-hoc:

```bash
uv run skills/confluence/scripts/confluence.py --page-id 123456 --host https://other.example.com --username other
```

Or call `npx` directly:

```bash
npx @acq-tech/confluence \
  --host https://confluence.example.com \
  --username myuser \
  --start-page-id 123456 \
  --folder-path ./docs \
  --recursive
```

## CLI Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--username <name>` | Confluence username (prompted if omitted) | — |
| `--folder-path <path>` | Local path for saved pages | `./docs` |
| `--recursive` | Download child pages recursively | false |
| `page` (positional) | Full URL to Confluence page | required |

## Notes

- The page URL is required — use the full Confluence page URL, or just the page ID (wrapper constructs the URL from config host)
- Output directory is created automatically if it doesn't exist
- **Back up existing docs or use version control before running** — existing files may be overwritten
