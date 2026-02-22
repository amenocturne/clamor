---
name: python
description: Python development patterns. Use when working on Python projects or writing Python code. Triggers on ".py files", "python project", "pytest", "pyproject.toml", working in a project with tech:[python].
author: amenocturne
---

# Python Development

Python with uv, ruff, and functional style.

## Stack

| Purpose | Tool |
|---------|------|
| Package manager | uv |
| Formatter | ruff format |
| Linter | ruff check |
| CLI framework | Click |
| Testing | pytest |
| Type checking | pyright or mypy |

## Commands

```bash
just setup       # uv sync
just test        # uv run pytest
just lint        # uv run ruff check .
just fmt         # uv run ruff format .
just fix         # uv run ruff check --fix .
```

## Running Python

**Never** use raw `python`. Always use `uv`:

```bash
uv run script.py           # Run script
uv run pytest              # Run tests
uv run ruff check .        # Lint
```

For standalone scripts, use PEP 723 inline metadata:

```python
#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["click", "rich"]
# ///
```

## Project Structure

```
project/
├── src/
│   └── project_name/
│       ├── __init__.py
│       ├── cli.py          # Click commands
│       ├── core.py         # Business logic (pure)
│       └── types.py        # Type definitions
├── tests/
│   └── test_core.py
├── pyproject.toml
└── justfile
```

## Type Hints

Always use type hints. Be explicit:

```python
from typing import TypeAlias
from collections.abc import Sequence, Mapping

UserId: TypeAlias = str
Config: TypeAlias = Mapping[str, str]

def process_users(users: Sequence[User], config: Config) -> list[ProcessedUser]:
    return [process_user(u, config) for u in users]

# Use | for unions (Python 3.10+)
def find_user(user_id: UserId) -> User | None:
    ...
```

## Functional Patterns

```python
# Pure functions
def calculate_score(items: list[Item]) -> int:
    return sum(item.value for item in items)

# Immutable data with dataclasses
from dataclasses import dataclass

@dataclass(frozen=True)
class User:
    id: str
    name: str
    score: int

# Transform, don't mutate
def update_score(user: User, delta: int) -> User:
    return User(id=user.id, name=user.name, score=user.score + delta)

# Use comprehensions
filtered = [x for x in items if x.active]
mapped = {item.id: item for item in items}
```

## CLI with Click

```python
import click

@click.group()
def cli():
    """Project CLI."""
    pass

@cli.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--verbose', '-v', is_flag=True)
def process(path: str, verbose: bool):
    """Process a file."""
    if verbose:
        click.echo(f"Processing {path}")

if __name__ == '__main__':
    cli()
```

## Testing

```python
import pytest
from project.core import calculate_score, Item

def test_calculate_score_empty():
    assert calculate_score([]) == 0

def test_calculate_score_multiple():
    items = [Item(value=10), Item(value=20)]
    assert calculate_score(items) == 30

@pytest.fixture
def sample_config() -> Config:
    return {"key": "value"}
```

## pyproject.toml

```toml
[project]
name = "project-name"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["click", "rich"]

[project.scripts]
project-name = "project_name.cli:cli"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

## Anti-patterns

- Running `python` directly (use `uv run`)
- Mutable default arguments (`def f(items=[])`)
- Global state
- Classes when dataclasses suffice
- `import *`
- Catching bare `Exception`
