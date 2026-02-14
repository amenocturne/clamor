#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "rich"]
# ///
"""
Install agent-kit presets into a target directory.

Usage:
    uv run install.py                           # Interactive preset selection
    uv run install.py --presets base frontend   # Specify presets directly
    uv run install.py --list                    # List available presets
"""

import argparse
import json
import shutil
from pathlib import Path

import yaml
from rich.console import Console
from rich.prompt import Prompt

console = Console()

REPO_ROOT = Path(__file__).parent
PRESETS_DIR = REPO_ROOT / "presets"
SKILLS_DIR = REPO_ROOT / "skills"
HOOKS_DIR = REPO_ROOT / "hooks"
PIPELINES_DIR = REPO_ROOT / "pipelines"


def load_manifest(preset: str) -> dict:
    """Load manifest.yaml for a preset."""
    manifest_path = PRESETS_DIR / preset / "manifest.yaml"
    if not manifest_path.exists():
        console.print(f"[red]Preset '{preset}' not found[/red]")
        return {}
    return yaml.safe_load(manifest_path.read_text())


def load_hook_config(hook_name: str, hook_dir: Path) -> dict:
    """Load hooks.json from a hook directory and resolve {hook_dir} placeholders."""
    hooks_json = HOOKS_DIR / hook_name / "hooks.json"
    if not hooks_json.exists():
        return {}

    content = hooks_json.read_text().replace("{hook_dir}", str(hook_dir))
    return json.loads(content)


def merge_hooks(base: dict, new: dict) -> dict:
    """Merge hook configurations, combining arrays for each hook type."""
    for hook_type, hooks in new.items():
        if hook_type not in base:
            base[hook_type] = []
        base[hook_type].extend(hooks)
    return base


def load_existing_settings(target: Path) -> dict:
    """Load existing .claude/settings.json if it exists."""
    settings_path = target / ".claude" / "settings.json"
    if settings_path.exists():
        return json.loads(settings_path.read_text())
    return {"hooks": {}}


def merge_settings(presets: list[str], target: Path) -> dict:
    """Merge settings.json from all presets with existing settings."""
    merged = load_existing_settings(target)
    if "hooks" not in merged:
        merged["hooks"] = {}

    for preset in presets:
        settings_path = PRESETS_DIR / preset / "settings.json"
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            merge_hooks(merged["hooks"], settings.get("hooks", {}))
    return merged


def merge_claude_md(presets: list[str]) -> str:
    """Concatenate claude.md from all presets with headers."""
    sections = []
    for preset in presets:
        claude_path = PRESETS_DIR / preset / "claude.md"
        if claude_path.exists():
            sections.append(f"# From {preset}\n\n{claude_path.read_text()}")
    return "\n\n".join(sections)


def collect_components(presets: list[str]) -> dict:
    """Collect all skills, hooks, pipelines from manifests."""
    components = {
        "skills": set(),
        "hooks": set(),
        "pipelines": set(),
        "external": set(),
    }
    for preset in presets:
        manifest = load_manifest(preset)
        for key in components:
            components[key].update(manifest.get(key, []))
    return components


def resolve_dependencies(components: dict) -> dict:
    """Add dependencies (e.g., workspace pipeline needs link-proxy)."""
    if "workspace" in components["pipelines"]:
        components["hooks"].add("link-proxy")
    return components


def install(presets: list[str], target: Path):
    """Main installation logic."""
    console.print(f"[bold]Installing presets:[/bold] {', '.join(presets)}")

    components = collect_components(presets)
    components = resolve_dependencies(components)

    target_claude = target / ".claude"
    target_claude.mkdir(parents=True, exist_ok=True)

    # Merge settings from presets with existing settings
    settings = merge_settings(presets, target)

    # Add hook configurations from hooks.json files
    for hook in components["hooks"]:
        hook_dir = target_claude / "hooks" / hook
        hook_config = load_hook_config(hook, hook_dir)
        merge_hooks(settings["hooks"], hook_config)

    (target_claude / "settings.json").write_text(json.dumps(settings, indent=2))
    console.print("  [green]✓[/green] .claude/settings.json")

    # Symlink or merge .claude/CLAUDE.md (preset instructions)
    # Root CLAUDE.md is left for user's project-specific instructions
    target_claude_md = target_claude / "CLAUDE.md"
    if target_claude_md.exists() or target_claude_md.is_symlink():
        target_claude_md.unlink()
    if len(presets) == 1:
        # Single preset: symlink for auto-sync
        src = PRESETS_DIR / presets[0] / "claude.md"
        if src.exists():
            target_claude_md.symlink_to(src)
            console.print("  [green]✓[/green] .claude/CLAUDE.md (symlinked)")
    else:
        # Multiple presets: merge content
        claude_md = merge_claude_md(presets)
        target_claude_md.write_text(claude_md)
        console.print("  [green]✓[/green] .claude/CLAUDE.md (merged)")

    # Symlink instructions folder from presets
    for preset in presets:
        instructions_src = PRESETS_DIR / preset / "instructions"
        if instructions_src.exists():
            instructions_dst = target_claude / "instructions"
            if instructions_dst.exists() or instructions_dst.is_symlink():
                if instructions_dst.is_symlink():
                    instructions_dst.unlink()
                else:
                    shutil.rmtree(instructions_dst)
            instructions_dst.symlink_to(instructions_src)
            console.print("  [green]✓[/green] .claude/instructions/ (symlinked)")

    # Symlink templates folder from presets
    for preset in presets:
        templates_src = PRESETS_DIR / preset / "templates"
        if templates_src.exists():
            templates_dst = target_claude / "templates"
            if templates_dst.exists() or templates_dst.is_symlink():
                if templates_dst.is_symlink():
                    templates_dst.unlink()
                else:
                    shutil.rmtree(templates_dst)
            templates_dst.symlink_to(templates_src)
            console.print("  [green]✓[/green] .claude/templates/ (symlinked)")

    # Symlink skills
    skills_dir = target_claude / "skills"
    skills_dir.mkdir(exist_ok=True)
    for skill in components["skills"]:
        src = SKILLS_DIR / skill
        dst = skills_dir / skill
        if src.exists() and not dst.exists():
            dst.symlink_to(src)
            console.print(f"  [green]✓[/green] Skill: {skill}")

    # Symlink hooks into .claude/hooks/
    hooks_target = target_claude / "hooks"
    hooks_target.mkdir(exist_ok=True)
    for hook in components["hooks"]:
        src = HOOKS_DIR / hook
        dst = hooks_target / hook
        if src.exists() and not dst.exists():
            dst.symlink_to(src)
            console.print(f"  [green]✓[/green] Hook: {hook}")

    # Symlink pipelines
    pipelines_target = target / "pipelines"
    if components["pipelines"]:
        pipelines_target.mkdir(exist_ok=True)
    for pipeline in components["pipelines"]:
        src = PIPELINES_DIR / pipeline
        dst = pipelines_target / pipeline
        if src.exists() and not dst.exists():
            dst.symlink_to(src)
            console.print(f"  [green]✓[/green] Pipeline: {pipeline}")

    # Print external recommendations
    if components["external"]:
        console.print("\n[bold]Recommended external skills:[/bold]")
        for ext in components["external"]:
            console.print(f"  npx skills add {ext}")

    console.print("\n[bold green]Done![/bold green]")


def list_presets():
    """List all available presets."""
    console.print("[bold]Available presets:[/bold]")
    for preset in sorted(PRESETS_DIR.iterdir()):
        if preset.is_dir():
            manifest = load_manifest(preset.name)
            desc = manifest.get("description", "")
            console.print(f"  [cyan]{preset.name}[/cyan]: {desc}")


def main():
    parser = argparse.ArgumentParser(description="Install agent-kit presets")
    parser.add_argument("--presets", nargs="+", help="Presets to install")
    parser.add_argument(
        "--target", type=Path, default=Path.cwd(), help="Target directory"
    )
    parser.add_argument("--list", action="store_true", help="List available presets")
    args = parser.parse_args()

    if args.list:
        list_presets()
        return

    if args.presets:
        presets = args.presets
    else:
        # Interactive selection
        available = sorted([p.name for p in PRESETS_DIR.iterdir() if p.is_dir()])
        console.print("[bold]Available presets:[/bold]")
        for i, p in enumerate(available, 1):
            manifest = load_manifest(p)
            desc = manifest.get("description", "")
            console.print(f"  {i}. [cyan]{p}[/cyan]: {desc}")
        selection = Prompt.ask("\nSelect presets (comma-separated numbers)")
        indices = [int(x.strip()) - 1 for x in selection.split(",")]
        presets = [available[i] for i in indices if 0 <= i < len(available)]

    if not presets:
        console.print("[red]No presets selected[/red]")
        return

    install(presets, args.target)


if __name__ == "__main__":
    main()
