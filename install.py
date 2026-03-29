#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "rich"]
# ///
"""
Install an agent-kit preset into a target directory.

Usage:
    uv run install.py
    uv run install.py --preset knowledge-base
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
    load_json,
    load_registry as load_registry_file,
    merge_hooks,
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
PRESETS_DIR = REPO_ROOT / "presets"
SKILLS_DIR = REPO_ROOT / "skills"
HOOKS_DIR = REPO_ROOT / "hooks"
PIPELINES_DIR = REPO_ROOT / "pipelines"
COMMON_DIR = REPO_ROOT / "common"
REGISTRY_PATH = REPO_ROOT / "installations.yaml"
LEGACY_AGENTS = ["claude-code"]

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


def load_manifest(preset: str) -> dict:
    manifest_path = PRESETS_DIR / preset / "manifest.yaml"
    if not manifest_path.exists():
        console.print(f"[red]Preset '{preset}' not found[/red]")
        return {}
    return yaml.safe_load(manifest_path.read_text()) or {}


def load_hook_config(hook_name: str, hook_dir: Path) -> dict:
    return load_hook_config_from_root(hook_name, hook_dir, HOOKS_DIR)


def sync_symlinks(source_dir: Path, target_dir: Path, wanted: set[str], label: str):
    sync_symlinks_with_console(source_dir, target_dir, wanted, label, console=console)


def load_existing_settings(target: Path) -> dict:
    return load_json(
        target / ".claude" / "settings.json", {"hooks": {}, "permissions": {}}
    )


def merge_permissions(existing: dict, new: dict):
    for key in ["allow", "deny"]:
        if key not in new:
            continue
        existing.setdefault(key, [])
        for perm in new[key]:
            if perm not in existing[key]:
                existing[key].append(perm)


def merge_settings(preset: str, target: Path) -> dict:
    merged = load_existing_settings(target)
    merged["hooks"] = {}

    settings_path = PRESETS_DIR / preset / "settings.json"
    if settings_path.exists():
        settings = load_json(settings_path)
        merge_hooks(merged["hooks"], settings.get("hooks", {}))
        if "permissions" in settings:
            merged.setdefault("permissions", {})
            merge_permissions(merged["permissions"], settings["permissions"])
    return merged


def collect_components(preset: str) -> dict:
    manifest = load_manifest(preset)
    return {
        "skills": set(normalize_manifest_list(manifest.get("skills"))),
        "hooks": set(normalize_manifest_list(manifest.get("hooks"))),
        "pipelines": set(normalize_manifest_list(manifest.get("pipelines"))),
        "external": set(normalize_manifest_list(manifest.get("external"))),
        "instructions": normalize_manifest_list(manifest.get("instructions")),
        "common": normalize_manifest_list(manifest.get("common")),
        "agents": normalize_manifest_list(manifest.get("agents"))
        if "agents" in manifest
        else None,
    }


def resolve_dependencies(components: dict) -> dict:
    if "workspace" in components["pipelines"]:
        components["hooks"].add("link-proxy")
    return components


def load_registry() -> list[dict]:
    return load_registry_file(REGISTRY_PATH)


def save_registry(entries: list[dict]):
    save_registry_file(entries, REGISTRY_PATH)


def update_registry(
    preset: str,
    target: Path,
    knowledge_base: Path | None = None,
    agents: list[str] | None = None,
    project_dirs: dict[str, Path] | None = None,
):
    entries = load_registry()
    target_str = str(target.resolve())

    entry: dict[str, Any] = {"preset": preset, "target": target_str}
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


def available_agents() -> list[str]:
    result = []
    agents_dir = REPO_ROOT / "agents"
    for path in sorted(agents_dir.iterdir()):
        if path.is_dir() and (path / "install.py").exists():
            result.append(path.name)
    return result


def require_agents(preset: str, manifest: dict) -> list[str]:
    if "agents" not in manifest:
        supported = ", ".join(available_agents())
        raise ValueError(
            f"Preset '{preset}' must declare 'agents:' explicitly. "
            f"Choose one or more supported agents: {supported}."
        )

    agents = normalize_manifest_list(manifest.get("agents"))
    if not agents:
        supported = ", ".join(available_agents())
        raise ValueError(
            f"Preset '{preset}' has an empty 'agents:' list. "
            f"Choose one or more supported agents: {supported}."
        )

    unknown = [agent for agent in agents if agent not in available_agents()]
    if unknown:
        supported = ", ".join(available_agents())
        raise ValueError(
            f"Preset '{preset}' requests unsupported agents: {', '.join(unknown)}. "
            f"Supported agents: {supported}."
        )
    return agents


def load_agent_installer(agent_name: str) -> Any:
    cached = _AGENT_INSTALLERS.get(agent_name)
    if cached is not None:
        return cached

    install_path = REPO_ROOT / "agents" / agent_name / "install.py"
    if not install_path.exists():
        raise FileNotFoundError(f"Agent installer not found for '{agent_name}'")

    module_name = f"agent_installer_{agent_name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, install_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load installer for '{agent_name}'")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _AGENT_INSTALLERS[agent_name] = module
    return module


def project_dirs_for_agents(target: Path, agents: list[str]) -> dict[str, Path]:
    project_dirs = {}
    for agent in agents:
        installer = load_agent_installer(agent)
        dirname = getattr(installer, "AGENT_DIRNAME", None)
        if not dirname:
            raise ValueError(f"Agent installer '{agent}' is missing AGENT_DIRNAME")
        project_dirs[agent] = target / dirname
    return project_dirs


def registry_agents_for_reinstall(entry: dict) -> list[str] | None:
    if "agents" in entry:
        return normalize_manifest_list(entry.get("agents"))
    return list(LEGACY_AGENTS)


def choose_preset_interactively() -> str | None:
    available = sorted([p.name for p in PRESETS_DIR.iterdir() if p.is_dir()])
    console.print("[bold]Available presets:[/bold]")
    for i, p in enumerate(available, 1):
        manifest = load_manifest(p)
        desc = manifest.get("description", "")
        console.print(f"  {i}. [cyan]{p}[/cyan]: {desc}")

    selection = Prompt.ask("\nSelect preset (number)")
    try:
        idx = int(selection.strip()) - 1
    except ValueError:
        console.print("[red]Invalid selection[/red]")
        return None
    if 0 <= idx < len(available):
        return available[idx]

    console.print("[red]Invalid selection[/red]")
    return None


def install_interactive(
    target: Path | None = None, knowledge_base: Path | None = None
) -> bool:
    preset = choose_preset_interactively()
    if preset is None:
        return False

    install(preset, target or Path.cwd(), knowledge_base)
    return True


def install_all() -> int:
    entries = load_registry()
    if not entries:
        console.print(
            "[yellow]No installations registered yet. Starting interactive install...[/yellow]"
        )
        return 1 if install_interactive() else 0

    success = 0
    for entry in entries:
        preset = entry["preset"]
        target = Path(entry["target"])
        kb = Path(entry["knowledge_base"]) if entry.get("knowledge_base") else None
        agents = registry_agents_for_reinstall(entry)
        console.print(f"\n[bold]━━━ {preset} → {target} ━━━[/bold]")
        try:
            install(preset, target, kb, agents=agents)
            success += 1
        except Exception as e:
            console.print(f"[red]Failed: {e}[/red]")
    return success


def install(
    preset: str,
    target: Path,
    knowledge_base: Path | None = None,
    *,
    agents: list[str] | None = None,
):
    console.print(f"[bold]Installing preset:[/bold] {preset}")

    manifest = load_manifest(preset)
    manifest_agents = require_agents(preset, manifest)
    selected_agents = list(agents) if agents is not None else manifest_agents
    unknown = [agent for agent in selected_agents if agent not in available_agents()]
    if unknown:
        raise ValueError(
            f"Unsupported agents selected for install: {', '.join(unknown)}"
        )

    components = resolve_dependencies(collect_components(preset))
    project_dirs = project_dirs_for_agents(target, selected_agents)

    console.print(f"  [green]✓[/green] Agents: {', '.join(selected_agents)}")

    for agent in selected_agents:
        installer = load_agent_installer(agent)
        ctx = InstallContext(
            target_dir=target,
            project_dir=project_dirs[agent],
            repo_root=REPO_ROOT,
            preset_name=preset,
            preset_dir=PRESETS_DIR / preset,
            skills=sorted(components["skills"]),
            hooks=sorted(components["hooks"]),
            common=list(components["common"]),
            external=sorted(components["external"]),
            pipelines=sorted(components["pipelines"]),
            instructions=list(components["instructions"]),
            all_agents=list(selected_agents),
            project_dirs=project_dirs,
            install_state_path=project_dirs[agent] / "agentic-kit.json",
            knowledge_base=knowledge_base,
        )
        installer.install(ctx, console=console)

    if components["external"]:
        console.print("\n[bold]Recommended external skills:[/bold]")
        for ext in sorted(components["external"]):
            console.print(f"  npx skills add {ext}")

    update_registry(
        preset,
        target,
        knowledge_base,
        agents=selected_agents,
        project_dirs=project_dirs,
    )
    console.print("\n[bold green]Done![/bold green]")


def list_presets():
    console.print("[bold]Available presets:[/bold]")
    for preset in sorted(PRESETS_DIR.iterdir()):
        if preset.is_dir():
            manifest = load_manifest(preset.name)
            desc = manifest.get("description", "")
            console.print(f"  [cyan]{preset.name}[/cyan]: {desc}")


def main():
    parser = argparse.ArgumentParser(description="Install an agent-kit preset")
    parser.add_argument("--preset", help="Preset to install")
    parser.add_argument(
        "--target", type=Path, default=Path.cwd(), help="Target directory"
    )
    parser.add_argument("--list", action="store_true", help="List available presets")
    parser.add_argument(
        "--knowledge-base",
        type=Path,
        help="Path to knowledge base (Obsidian vault) for integration",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="install_all",
        help="Reinstall all registered installations",
    )
    args = parser.parse_args()

    if args.list:
        list_presets()
        return

    if args.install_all:
        install_all()
        return

    if args.preset:
        preset = args.preset
    else:
        preset = choose_preset_interactively()
        if preset is None:
            return

    try:
        install(preset, args.target, args.knowledge_base)
    except KeyboardInterrupt:
        console.print(
            "\n[bold yellow]Installation interrupted.[/bold yellow] "
            "Target may be in a partial state. Re-run install to fix."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
