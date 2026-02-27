#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "rich"]
# ///
"""
Generate WORKSPACE.yaml from git repositories.

Scans for git repos and detects tech stacks from build files.

Usage:
    uv run generate-workspace.py [--root PATH] [--output PATH]
"""

import argparse
import subprocess
from pathlib import Path

import yaml
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)

# Build file -> (tech, tools) mapping
TECH_DETECTORS = {
    "build.sbt": (["scala"], ["sbt"]),
    "package.json": (["javascript", "typescript"], ["npm"]),
    "Cargo.toml": (["rust"], ["cargo"]),
    "go.mod": (["go"], []),
    "pyproject.toml": (["python"], ["uv"]),
    "build.gradle": (["kotlin", "java"], ["gradle"]),
    "build.gradle.kts": (["kotlin", "java"], ["gradle"]),
    "Package.swift": (["swift"], ["spm"]),
}

# Patterns that match path segments (for directories like .xcodeproj)
TECH_PATH_PATTERNS = {
    ".xcodeproj/": (["swift"], ["xcode"]),
}

# File extensions -> tech (for config-only repos)
TECH_EXTENSIONS = {
    (".yaml", ".yml"): (["yaml"], []),
}

# Default commands by tool
DEFAULT_COMMANDS = {
    "sbt": {
        "format_cmd": "sbt scalafmtAll",
        "lint_cmd": "sbt 'scalafixAll --check'",
        "test_cmd": "sbt test",
    },
    "npm": {
        "format_cmd": "npm run format",
        "lint_cmd": "npm run lint",
        "test_cmd": "npm test",
    },
    "cargo": {
        "format_cmd": "cargo fmt",
        "lint_cmd": "cargo clippy",
        "test_cmd": "cargo test",
    },
    "uv": {
        "format_cmd": "uv run ruff format .",
        "lint_cmd": "uv run ruff check .",
        "test_cmd": "uv run pytest",
    },
    "gradle": {
        "format_cmd": None,
        "lint_cmd": "./gradlew check",
        "test_cmd": "./gradlew test",
    },
    "xcode": {
        "format_cmd": None,
        "lint_cmd": None,
        "test_cmd": "xcodebuild test",
    },
    "spm": {
        "format_cmd": None,
        "lint_cmd": None,
        "test_cmd": "swift test",
    },
}


def find_git_repos(root: Path) -> list[Path]:
    """Find all git repositories recursively, excluding nested repos."""
    repos = []

    def scan(path: Path, inside_repo: bool = False):
        if not path.is_dir():
            return

        is_repo = (path / ".git").exists()

        if is_repo and not inside_repo:
            repos.append(path)
            # Don't scan inside repos (skip submodules, nested repos)
            return

        # Continue scanning subdirectories
        try:
            for child in sorted(path.iterdir()):
                if child.is_dir() and not child.name.startswith("."):
                    scan(child, inside_repo or is_repo)
        except PermissionError:
            pass

    scan(root)
    return repos


def get_tracked_files(repo: Path) -> set[str]:
    """Get list of tracked files using git ls-files (fast, respects .gitignore)."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return set(result.stdout.splitlines())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return set()


def detect_tech_stack(repo: Path) -> tuple[list[str], list[str]]:
    """Detect tech stack from build files in repo using git index."""
    techs = set()
    tools = set()

    tracked_files = get_tracked_files(repo)

    # Check for exact filename matches
    for filename, (tech_list, tool_list) in TECH_DETECTORS.items():
        for tracked in tracked_files:
            if tracked == filename or tracked.endswith("/" + filename):
                techs.update(tech_list)
                tools.update(tool_list)
                break

    # Check path patterns (for directories like .xcodeproj/)
    for pattern, (tech_list, tool_list) in TECH_PATH_PATTERNS.items():
        for tracked in tracked_files:
            if pattern in tracked:
                techs.update(tech_list)
                tools.update(tool_list)
                break

    # Check file extensions (for config-only repos)
    for extensions, (tech_list, tool_list) in TECH_EXTENSIONS.items():
        for tracked in tracked_files:
            if tracked.endswith(extensions):
                techs.update(tech_list)
                tools.update(tool_list)
                break

    # Fallback: check root directory for untracked build files (new repos)
    if not techs and not tools:
        for filename, (tech_list, tool_list) in TECH_DETECTORS.items():
            if (repo / filename).exists():
                techs.update(tech_list)
                tools.update(tool_list)

    return sorted(techs), sorted(tools)


def get_commands(tools: list[str]) -> dict[str, str | None]:
    """Get default commands for the first matching tool."""
    for tool in tools:
        if tool in DEFAULT_COMMANDS:
            return DEFAULT_COMMANDS[tool].copy()
    return {"format_cmd": None, "lint_cmd": None, "test_cmd": None}


def generate_project_entry(repo: Path, root_dir: Path) -> dict:
    """Generate a project entry for WORKSPACE.yaml."""
    techs, tools = detect_tech_stack(repo)
    commands = get_commands(tools)

    # Build relative path
    rel_path = "./" + repo.relative_to(root_dir).as_posix()

    entry = {
        "path": rel_path,
        "description": "TODO: describe this project",
        "tech": techs + tools if techs or tools else ["unknown"],
        "explore_when": [],
        "entry_points": [],
    }

    # Add commands if detected
    if commands["format_cmd"]:
        entry["format_cmd"] = commands["format_cmd"]
    if commands["lint_cmd"]:
        entry["lint_cmd"] = commands["lint_cmd"]
    if commands["test_cmd"]:
        entry["test_cmd"] = commands["test_cmd"]

    return entry


def generate_workspace(root_dir: Path, progress: Progress) -> dict:
    """Generate the complete WORKSPACE.yaml structure."""
    # Phase 1: Find repos
    scan_task = progress.add_task("[cyan]Scanning for repos...", total=None)
    repos = find_git_repos(root_dir)
    progress.remove_task(scan_task)

    # Phase 2: Process repos
    process_task = progress.add_task(
        "[green]Detecting tech stacks...", total=len(repos)
    )
    projects = {}
    for repo in repos:
        rel_path = repo.relative_to(root_dir).as_posix()
        progress.update(process_task, description=f"[green]Processing {rel_path}")
        projects[rel_path] = generate_project_entry(repo, root_dir)
        progress.advance(process_task)

    return {"version": 1, "projects": projects}


def main():
    parser = argparse.ArgumentParser(
        description="Generate WORKSPACE.yaml from git repos"
    )
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Root directory to scan"
    )
    parser.add_argument(
        "--output", type=Path, default=Path("WORKSPACE.yaml"), help="Output file"
    )
    args = parser.parse_args()

    console = Console()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        workspace = generate_workspace(args.root, progress)

    # Custom YAML representer to use flow style for lists
    def list_representer(dumper, data):
        if len(data) <= 4 and all(isinstance(x, str) and len(x) < 20 for x in data):
            return dumper.represent_sequence(
                "tag:yaml.org,2002:seq", data, flow_style=True
            )
        return dumper.represent_sequence(
            "tag:yaml.org,2002:seq", data, flow_style=False
        )

    yaml.add_representer(list, list_representer)

    yaml_content = yaml.dump(
        workspace,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )

    args.output.write_text(yaml_content)
    console.print(f"[bold green]Generated[/] {args.output}")
    console.print(f"Found [bold]{len(workspace['projects'])}[/] projects:")
    for name, project in workspace["projects"].items():
        tech_str = ", ".join(project["tech"])
        console.print(f"  [dim]•[/] [cyan]{name}[/]: {tech_str}")


if __name__ == "__main__":
    main()
