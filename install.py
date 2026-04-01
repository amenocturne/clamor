#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "rich"]
# ///
"""
Install agentic-kit: profile × agent architecture.

Usage:
    uv run install.py --profile personal --agents claude-code pi
    uv run install.py --all
    uv run install.py --list
"""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
from typing import Any

import yaml
from lib.install_types import InstallContext
from lib.install_utils import (
    extract_common_names_from_template,
    get_hook_key,
    load_hook_config as load_hook_config_from_root,
    load_registry as load_registry_file,
    merge_manifests,
    normalize_manifest_list,
    parse_frontmatter,
    process_includes as process_includes_from_root,
    save_registry as save_registry_file,
    strip_frontmatter,
    sync_symlinks as sync_symlinks_with_console,
    validate_common_dependencies as validate_common_dependencies_in_dir,
)
from rich.console import Console
from rich.prompt import Prompt

console = Console()

REPO_ROOT = Path(__file__).parent
PROFILES_DIR = REPO_ROOT / "profiles"
AGENTS_DIR = REPO_ROOT / "agents"
SKILLS_DIR = REPO_ROOT / "skills"
HOOKS_DIR = REPO_ROOT / "hooks"
PIPELINES_DIR = REPO_ROOT / "pipelines"
COMMON_DIR = REPO_ROOT / "common"
REGISTRY_PATH = REPO_ROOT / "installations.yaml"

_AGENT_INSTALLERS: dict[str, Any] = {}

__all__ = [
    "extract_common_names_from_template",
    "get_hook_key",
    "parse_frontmatter",
    "strip_frontmatter",
]


def process_includes(content: str) -> str:
    return process_includes_from_root(content, REPO_ROOT)


def validate_common_dependencies(
    common_names: list[str], available_skills: set[str]
) -> list[str]:
    return validate_common_dependencies_in_dir(
        common_names, available_skills, COMMON_DIR
    )


def load_hook_config(hook_name: str, hook_dir: Path) -> dict:
    return load_hook_config_from_root(hook_name, hook_dir, HOOKS_DIR)


def sync_symlinks(source_dir: Path, target_dir: Path, wanted: set[str], label: str):
    sync_symlinks_with_console(source_dir, target_dir, wanted, label, console=console)


# ---------------------------------------------------------------------------
# Profile / Agent manifest loading
# ---------------------------------------------------------------------------


def load_profile_manifest(profile: str) -> dict:
    path = PROFILES_DIR / profile / "manifest.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Profile '{profile}' not found at {path}")
    return yaml.safe_load(path.read_text()) or {}


def load_agent_manifest(agent: str) -> dict:
    path = AGENTS_DIR / agent / "manifest.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Agent manifest not found for '{agent}' at {path}")
    return yaml.safe_load(path.read_text()) or {}


def available_profiles() -> list[str]:
    if not PROFILES_DIR.exists():
        return []
    return sorted(
        p.name
        for p in PROFILES_DIR.iterdir()
        if p.is_dir() and (p / "manifest.yaml").exists()
    )


def available_agents() -> list[str]:
    """List agents that have a manifest.yaml (v2) or install.py (v1 runtime)."""
    result = set()
    for path in sorted(AGENTS_DIR.iterdir()):
        if path.is_dir() and (path / "manifest.yaml").exists():
            result.add(path.name)
    return sorted(result)


def available_runtimes() -> list[str]:
    """List agent runtimes that have an install.py."""
    result = []
    for path in sorted(AGENTS_DIR.iterdir()):
        if path.is_dir() and (path / "install.py").exists():
            result.append(path.name)
    return result


# ---------------------------------------------------------------------------
# Agent installer loading (by runtime)
# ---------------------------------------------------------------------------


def load_agent_installer(runtime: str) -> Any:
    """Load the install.py module for a given runtime (e.g., 'claude-code', 'pi')."""
    cached = _AGENT_INSTALLERS.get(runtime)
    if cached is not None:
        return cached

    install_path = AGENTS_DIR / runtime / "install.py"
    if not install_path.exists():
        raise FileNotFoundError(
            f"Runtime installer not found for '{runtime}' at {install_path}"
        )

    module_name = f"agent_installer_{runtime.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, install_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load installer for runtime '{runtime}'")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _AGENT_INSTALLERS[runtime] = module
    return module


def resolve_runtime(agent_name: str, agent_manifest: dict) -> str:
    """Get the runtime for an agent. Falls back to agent_name if not specified."""
    return agent_manifest.get("runtime", agent_name)


def project_dir_for_agent(target: Path, agent_manifest: dict) -> Path:
    """Get the project directory for an agent from its manifest's target field."""
    dirname = agent_manifest.get("target")
    if not dirname:
        raise ValueError("Agent manifest missing 'target' field")
    return target / dirname


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def load_registry() -> list[dict]:
    return load_registry_file(REGISTRY_PATH)


def save_registry(entries: list[dict]):
    save_registry_file(entries, REGISTRY_PATH)


def update_registry(
    profile: str,
    target: Path,
    knowledge_base: Path | None = None,
    agents: list[str] | None = None,
    project_dirs: dict[str, Path] | None = None,
):
    entries = load_registry()
    target_str = str(target.resolve())

    entry: dict[str, Any] = {"profile": profile, "target": target_str}
    if knowledge_base is not None:
        entry["knowledge_base"] = str(knowledge_base.resolve())
    if agents is not None:
        entry["agents"] = list(agents)
    if project_dirs is not None:
        entry["project_dirs"] = {
            name: str(path.resolve()) for name, path in sorted(project_dirs.items())
        }

    for i, existing in enumerate(entries):
        if existing.get("target") == target_str:
            entries[i] = entry
            save_registry(entries)
            return

    entries.append(entry)
    save_registry(entries)


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


def install(
    profile: str,
    agents: list[str],
    target: Path,
    knowledge_base: Path | None = None,
):
    console.print(
        f"[bold]Installing:[/bold] profile={profile}, agents={', '.join(agents)}"
    )

    profile_manifest = load_profile_manifest(profile)
    project_dirs: dict[str, Path] = {}

    for agent_name in agents:
        agent_manifest = load_agent_manifest(agent_name)
        merged = merge_manifests(profile_manifest, agent_manifest)

        runtime = resolve_runtime(agent_name, agent_manifest)
        installer = load_agent_installer(runtime)

        project_dir = project_dir_for_agent(target, agent_manifest)
        project_dirs[agent_name] = project_dir

        kb = knowledge_base
        if kb is None and profile_manifest.get("settings", {}).get("knowledge_base"):
            kb = Path(profile_manifest["settings"]["knowledge_base"])

        ctx = InstallContext(
            target_dir=target,
            project_dir=project_dir,
            repo_root=REPO_ROOT,
            profile_name=profile,
            profile_dir=PROFILES_DIR / profile,
            agent_name=agent_name,
            agent_dir=AGENTS_DIR / agent_name,
            skills=merged["skills"],
            hooks=merged["hooks"],
            common=merged["common"],
            external=merged["external"],
            pipelines=merged["pipelines"],
            extensions=merged["extensions"],
            instructions=merged["instructions"],
            settings=merged["settings"],
            all_agents=list(agents),
            project_dirs=project_dirs,
            install_state_path=project_dir / "agentic-kit.json",
            knowledge_base=kb,
        )
        installer.install(ctx, console=console)
        console.print(f"  [green]✓[/green] {agent_name} → {project_dir}")

    if merged.get("external"):
        console.print("\n[bold]Recommended external skills:[/bold]")
        for ext in sorted(merged["external"]):
            console.print(f"  npx skills add {ext}")

    update_registry(
        profile,
        target,
        knowledge_base,
        agents=agents,
        project_dirs=project_dirs,
    )
    console.print("\n[bold green]Done![/bold green]")


# ---------------------------------------------------------------------------
# Reinstall all registered installations
# ---------------------------------------------------------------------------


def migrate_registry_entry(entry: dict) -> dict:
    """Migrate a v1 registry entry (preset-based) to v2 (profile-based)."""
    if "profile" in entry:
        return entry

    preset = entry.get("preset", "")
    profile_map = {
        "dev-workspace": "personal",
        "knowledge-base": "knowledge-base",
        "work": "work",
    }
    profile = profile_map.get(preset, preset)

    migrated = dict(entry)
    migrated["profile"] = profile
    del migrated["preset"]
    return migrated


def install_all() -> int:
    entries = load_registry()
    if not entries:
        console.print(
            "[yellow]No installations registered. Use --profile and --agents to install.[/yellow]"
        )
        return 0

    success = 0
    for entry in entries:
        entry = migrate_registry_entry(entry)
        profile = entry["profile"]
        target = Path(entry["target"])
        kb = Path(entry["knowledge_base"]) if entry.get("knowledge_base") else None
        agents = normalize_manifest_list(entry.get("agents"))
        if not agents:
            console.print(f"[yellow]Skipping {target}: no agents listed[/yellow]")
            continue
        console.print(f"\n[bold]━━━ {profile} → {target} ━━━[/bold]")
        try:
            install(profile, agents, target, kb)
            success += 1
        except Exception as e:
            console.print(f"[red]Failed: {e}[/red]")
    return success


# ---------------------------------------------------------------------------
# Interactive
# ---------------------------------------------------------------------------


def choose_profile_interactively() -> str | None:
    profiles = available_profiles()
    if not profiles:
        console.print("[red]No profiles found in profiles/[/red]")
        return None
    console.print("[bold]Available profiles:[/bold]")
    for i, p in enumerate(profiles, 1):
        try:
            manifest = load_profile_manifest(p)
            desc = manifest.get("description", "")
        except FileNotFoundError:
            desc = ""
        console.print(f"  {i}. [cyan]{p}[/cyan]: {desc}")

    selection = Prompt.ask("\nSelect profile (number)")
    try:
        idx = int(selection.strip()) - 1
    except ValueError:
        console.print("[red]Invalid selection[/red]")
        return None
    if 0 <= idx < len(profiles):
        return profiles[idx]

    console.print("[red]Invalid selection[/red]")
    return None


def choose_agents_interactively() -> list[str] | None:
    agents = available_agents()
    if not agents:
        console.print("[red]No agents found in agents/[/red]")
        return None
    console.print("[bold]Available agents:[/bold]")
    for i, a in enumerate(agents, 1):
        try:
            manifest = load_agent_manifest(a)
            desc = manifest.get("description", "")
        except FileNotFoundError:
            desc = ""
        console.print(f"  {i}. [cyan]{a}[/cyan]: {desc}")

    selection = Prompt.ask("\nSelect agents (comma-separated numbers, e.g. 1,3,4)")
    try:
        indices = [int(s.strip()) - 1 for s in selection.split(",")]
    except ValueError:
        console.print("[red]Invalid selection[/red]")
        return None

    selected = []
    for idx in indices:
        if 0 <= idx < len(agents):
            selected.append(agents[idx])
        else:
            console.print(f"[red]Invalid index: {idx + 1}[/red]")
            return None
    return selected if selected else None


def install_interactive(
    target: Path | None = None, knowledge_base: Path | None = None
) -> bool:
    profile = choose_profile_interactively()
    if profile is None:
        return False

    agents = choose_agents_interactively()
    if agents is None:
        return False

    install(profile, agents, target or Path.cwd(), knowledge_base)
    return True


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def list_available():
    console.print("[bold]Available profiles:[/bold]")
    for profile in available_profiles():
        try:
            manifest = load_profile_manifest(profile)
            desc = manifest.get("description", "")
        except FileNotFoundError:
            desc = ""
        console.print(f"  [cyan]{profile}[/cyan]: {desc}")

    console.print("\n[bold]Available agents:[/bold]")
    for agent in available_agents():
        try:
            manifest = load_agent_manifest(agent)
            desc = manifest.get("description", "")
            runtime = manifest.get("runtime", agent)
        except FileNotFoundError:
            desc = ""
            runtime = agent
        console.print(f"  [cyan]{agent}[/cyan] (runtime: {runtime}): {desc}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Install agentic-kit (profile × agent)"
    )
    parser.add_argument("--profile", help="Profile to install (e.g., personal, work)")
    parser.add_argument(
        "--agents",
        nargs="+",
        help="Agents to install (e.g., claude-code pi)",
    )
    parser.add_argument(
        "--target", type=Path, default=Path.cwd(), help="Target directory"
    )
    parser.add_argument(
        "--list", action="store_true", help="List available profiles and agents"
    )
    parser.add_argument(
        "--knowledge-base",
        type=Path,
        help="Path to knowledge base (Obsidian vault)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="install_all",
        help="Reinstall all registered installations",
    )
    args = parser.parse_args()

    if args.list:
        list_available()
        return

    if args.install_all:
        install_all()
        return

    if args.profile and args.agents:
        try:
            install(args.profile, args.agents, args.target, args.knowledge_base)
        except KeyboardInterrupt:
            console.print(
                "\n[bold yellow]Installation interrupted.[/bold yellow] "
                "Target may be in a partial state. Re-run install to fix."
            )
            raise SystemExit(1)
        return

    if args.profile or args.agents:
        if not args.profile:
            console.print("[red]--profile is required when --agents is specified[/red]")
            return
        if not args.agents:
            console.print("[red]--agents is required when --profile is specified[/red]")
            return

    if not install_interactive(args.target, args.knowledge_base):
        return


if __name__ == "__main__":
    main()
