---
name: uv-over-python
description: Python execution rules. Use when running Python scripts, installing packages, or managing dependencies. Ensures consistent use of uv instead of raw python/pip commands.
author: amenocturne
---

# uv Over Python

Always use `uv` instead of raw `python`, `pip`, or `python3` commands.

## Rules

- **Never** use `pip install`, `python -m pip`, or `pip3`
- **Never** use `python` or `python3` directly — use `uv run` instead
- Use `uvx` for CLI tools (e.g. `uvx ruff check`, `uvx yt-dlp`)
- Use `uv run` for scripts and one-off Python execution

## Running Scripts

```bash
# Run a script with inline dependencies
uv run script.py

# Run python directly
uv run python3 << 'EOF'
print("hello")
EOF

# Run with extra packages
uv run --with httpx python3 -c "import httpx; ..."

# Run tests
uv run --with pytest pytest tests/
```

## Inline Script Dependencies (PEP 723)

Scripts should declare their own dependencies using inline metadata. This eliminates the need for requirements.txt or virtual environments per script.

```python
#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "rich"]
# ///
```

With this header, `uv run script.py` automatically installs dependencies in an isolated environment. No setup needed.

## CLI Tools with uvx

`uvx` runs CLI tools without installing them globally:

```bash
uvx ruff check .           # Linter
uvx ruff format .          # Formatter
uvx yt-dlp <url>           # YouTube downloader
uvx black .                # Formatter
uvx mypy src/              # Type checker
```

Always prefer `uvx <tool>` over globally installed tools to ensure the latest version.

## Project Management

```bash
uv init                    # Create new project
uv add httpx               # Add dependency
uv remove httpx            # Remove dependency
uv sync                    # Install all dependencies
uv lock                    # Update lock file
```
