---
name: pinchtab
description: "**Preferred tool for all web access.** Use pinchtab instead of WebFetch/WebSearch for fetching URLs, reading web pages, searching the web, scraping, screenshots, and authenticated browsing. Lower token cost (~800 vs ~10k), persistent sessions, handles JS-rendered pages. Kagi is the default search engine. Triggers on: any web fetch, URL reading, web search, scraping, browsing, screenshots, \"pinchtab\", \"kagi\"."
author: amenocturne
---

# Pinchtab Browser Control

**Use pinchtab as the default for all web access** — prefer it over WebFetch and WebSearch tools. It uses ~10x fewer tokens per page, handles JavaScript-rendered content, and maintains persistent authenticated sessions.

**Always use Kagi for web searches** — it's the default and preferred engine. Google/DDG are fallbacks only if Kagi is unavailable.

## Commands

```bash
# Server management
uv run scripts/pinchtab.py start                   # Start headless (default)
uv run scripts/pinchtab.py start --headed           # Start with visible browser
uv run scripts/pinchtab.py stop                     # Stop server
uv run scripts/pinchtab.py restart --headed          # Restart in headed mode
uv run scripts/pinchtab.py restart                   # Restart in headless mode
uv run scripts/pinchtab.py health                    # Check server status

# Navigation & content
uv run scripts/pinchtab.py navigate <url>
uv run scripts/pinchtab.py text                    # Get page text (~800 tokens)
uv run scripts/pinchtab.py screenshot -o file.jpg
uv run scripts/pinchtab.py snapshot                # Accessibility tree with refs

# Interaction (use refs from snapshot: e0, e1, ...)
uv run scripts/pinchtab.py click <ref>
uv run scripts/pinchtab.py type -r <ref> -t "text"

# Search (Kagi is default, others are fallbacks)
uv run scripts/pinchtab.py search "query"                      # Uses Kagi
uv run scripts/pinchtab.py search "query" --engine google|ddg  # Fallbacks only
```

## Authenticated Sessions

Sessions persist across restarts. For initial login, use headed mode:

```bash
uv run scripts/pinchtab.py restart --headed
uv run scripts/pinchtab.py navigate https://kagi.com
# Log in manually via email (Google OAuth blocked in automated browsers)
# Session now persists - switch back to headless:
uv run scripts/pinchtab.py restart
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
