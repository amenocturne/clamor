---
name: pinchtab
description: Lightweight browser control for AI agents. Use for web scraping, screenshots, form filling, or authenticated browsing sessions. Lighter alternative to playwright for simple tasks. Triggers on "pinchtab", "browser session", "scrape page", "web automation".
author: amenocturne
---

# Pinchtab Browser Control

Lightweight HTTP-based browser automation with persistent sessions. Server auto-starts when needed.

## Commands

```bash
# Navigation & content
uv run scripts/pinchtab.py navigate <url>
uv run scripts/pinchtab.py text                    # Get page text (~800 tokens)
uv run scripts/pinchtab.py screenshot -o file.jpg
uv run scripts/pinchtab.py snapshot                # Accessibility tree with refs

# Interaction (use refs from snapshot: e0, e1, ...)
uv run scripts/pinchtab.py click <ref>
uv run scripts/pinchtab.py type -r <ref> -t "text"

# Search engines
uv run scripts/pinchtab.py search "query" --engine kagi|google|ddg
```

## Authenticated Sessions

Sessions persist across restarts. For initial login, use headed mode:

```bash
BRIDGE_HEADLESS=false pinchtab
uv run scripts/pinchtab.py navigate https://kagi.com
# Log in manually via email (Google OAuth blocked in automated browsers)
# Session now persists - restart pinchtab and you're still logged in
```

## Kagi Search

After logging in once:

```bash
uv run scripts/pinchtab.py search "your query" --engine kagi
uv run scripts/pinchtab.py text | jq .text
```

## vs Playwright

| | Pinchtab | Playwright |
|-|----------|------------|
| Token usage | ~800/page | ~10,000+/page |
| Session persistence | Yes | No |
| Best for | Scraping, auth sessions | Test suites, CI |
