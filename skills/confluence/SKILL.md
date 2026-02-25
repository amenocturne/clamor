---
name: confluence
description: Import Confluence pages to Markdown via @acq-tech/confluence CLI. Use when user mentions Confluence import, downloading wiki pages, or converting Confluence to Markdown. Triggers on "confluence", "wiki import", "импорт страниц", "confluence to markdown".
author: amenocturne
---

# Confluence

Import Confluence pages to local Markdown files using `@acq-tech/confluence`.

> **Important:** Do NOT read `.claude/agentic-kit.json` to check credentials — a hook redacts the host URL, making it look broken. The wrapper reads config directly from disk and works correctly without Claude inspecting it.

## Running Import

The wrapper reads `host` and `username` from `.claude/agentic-kit.json` automatically. Just run:

```bash
uv run .claude/skills/confluence/scripts/confluence.py --page-id 123456 --folder-path ./tmp/confluence
uv run .claude/skills/confluence/scripts/confluence.py --page-id 123456 --folder-path ./tmp/confluence --recursive
```

Override config values ad-hoc:

```bash
uv run .claude/skills/confluence/scripts/confluence.py --page-id 123456 --host https://other.example.com --username other
```

## CLI Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--page-id <id>` | Confluence page ID | required |
| `--folder-path <path>` | Local path for saved files | `./docs` |
| `--recursive` | Download child pages recursively | false |
| `--host <url>` | Override Confluence host from config | — |
| `--username <name>` | Override username from config | — |

## After Download

Read the downloaded `.md` file from `--folder-path` to present content to the user.

## First-time Setup

If credentials are not yet configured, add to `.claude/agentic-kit.json`:

```json
{
  "confluence": {
    "host": "https://confluence.example.com",
    "username": "yourname"
  }
}
```

Optionally create `.wiki.config.yml` for Jira link resolution and retry config:

```bash
npx @acq-tech/confluence generate-config
```
