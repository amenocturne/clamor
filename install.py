#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "rich"]
# ///
"""
Install an agent-kit preset into a target directory.

Usage:
    uv run install.py                      # Interactive preset selection
    uv run install.py --preset knowledge-base   # Specify preset directly
    uv run install.py --list               # List available presets
"""

import argparse
import json
import re
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
COMMON_DIR = REPO_ROOT / "common"

INCLUDE_PATTERN = r"\{\{include:([^}]+)\}\}"
FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content. Returns (metadata, body)."""
    match = FRONTMATTER_PATTERN.match(content)
    if match:
        metadata = yaml.safe_load(match.group(1)) or {}
        body = content[match.end() :]
        return metadata, body
    return {}, content


def strip_frontmatter(content: str) -> str:
    """Remove YAML frontmatter from content."""
    _, body = parse_frontmatter(content)
    return body


def process_includes(content: str) -> str:
    """Process {{include:path}} directives, replacing them with file contents."""

    def replace_include(match):
        include_path = match.group(1)
        full_path = REPO_ROOT / include_path
        if full_path.exists():
            return strip_frontmatter(full_path.read_text()).strip()
        else:
            raise FileNotFoundError(f"Include not found: {include_path}")

    return re.sub(INCLUDE_PATTERN, replace_include, content)


def validate_common_dependencies(
    common_names: list[str], available_skills: set[str]
) -> list[str]:
    """Check that common files' required skills are present in the preset.

    Returns a list of error messages. Empty list means all dependencies are satisfied.
    """
    errors = []
    for name in common_names:
        path = COMMON_DIR / f"{name}.md"
        if not path.exists():
            errors.append(f"Common file not found: {name}.md")
            continue
        metadata, _ = parse_frontmatter(path.read_text())
        required = set(metadata.get("required_skills") or [])
        missing = required - available_skills
        if missing:
            errors.append(
                f"{name}.md requires missing skills: {', '.join(sorted(missing))}"
            )
    return errors


def extract_common_names_from_template(content: str) -> list[str]:
    """Extract common file names from {{include:common/...}} directives."""
    names = []
    for match in re.finditer(INCLUDE_PATTERN, content):
        path = match.group(1)
        if path.startswith("common/"):
            names.append(path.removeprefix("common/").removesuffix(".md"))
    return names


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


def get_hook_key(hook_entry: dict) -> str | None:
    """Extract unique identifier from a hook entry (the command path)."""
    hooks_list = hook_entry.get("hooks", [])
    if hooks_list and "command" in hooks_list[0]:
        return hooks_list[0]["command"]
    return None


def merge_hooks(base: dict, new: dict) -> dict:
    """Merge hook configurations, deduplicating and overriding existing hooks."""
    for hook_type, new_hooks in new.items():
        if hook_type not in base:
            base[hook_type] = []

        # Build index of existing hooks by their command
        existing_by_key = {}
        for i, hook_entry in enumerate(base[hook_type]):
            key = get_hook_key(hook_entry)
            if key:
                existing_by_key[key] = i

        # Add or replace hooks
        for new_hook in new_hooks:
            key = get_hook_key(new_hook)
            if key and key in existing_by_key:
                # Replace existing hook with new version
                base[hook_type][existing_by_key[key]] = new_hook
            else:
                # Add new hook
                base[hook_type].append(new_hook)
                if key:
                    existing_by_key[key] = len(base[hook_type]) - 1

    return base


def sync_symlinks(source_dir: Path, target_dir: Path, wanted: set[str], label: str):
    """Sync symlinks in target_dir to match wanted set.

    Removes stale symlinks (pointing into source_dir but not in wanted),
    updates outdated ones, and creates missing ones.
    """
    target_dir.mkdir(exist_ok=True)

    for entry in sorted(target_dir.iterdir()):
        if not entry.is_symlink():
            continue
        link_target = entry.readlink()
        try:
            link_target.relative_to(source_dir)
        except ValueError:
            continue
        if entry.name not in wanted:
            entry.unlink()
            console.print(f"  [yellow]−[/yellow] {label}: {entry.name} (removed)")
        elif link_target != source_dir / entry.name:
            entry.unlink()
            entry.symlink_to(source_dir / entry.name)
            console.print(f"  [blue]↻[/blue] {label}: {entry.name} (updated)")

    for name in sorted(wanted):
        src = source_dir / name
        dst = target_dir / name
        if src.exists() and not dst.exists():
            dst.symlink_to(src)
            console.print(f"  [green]✓[/green] {label}: {name}")


def load_existing_settings(target: Path) -> dict:
    """Load existing .claude/settings.json if it exists."""
    settings_path = target / ".claude" / "settings.json"
    if settings_path.exists():
        return json.loads(settings_path.read_text())
    return {"hooks": {}, "permissions": {}}


def merge_permissions(existing: dict, new: dict):
    """Merge permissions from preset into existing permissions."""
    for key in ["allow", "deny"]:
        if key in new:
            if key not in existing:
                existing[key] = []
            # Add new permissions, avoiding duplicates
            for perm in new[key]:
                if perm not in existing[key]:
                    existing[key].append(perm)


def merge_settings(preset: str, target: Path) -> dict:
    """Merge preset settings.json with existing settings."""
    merged = load_existing_settings(target)
    # Always start fresh with hooks to avoid stale entries
    merged["hooks"] = {}

    settings_path = PRESETS_DIR / preset / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        merge_hooks(merged["hooks"], settings.get("hooks", {}))
        # Merge permissions
        if "permissions" in settings:
            if "permissions" not in merged:
                merged["permissions"] = {}
            merge_permissions(merged["permissions"], settings["permissions"])
    return merged


def collect_components(preset: str) -> dict:
    """Collect all skills, hooks, pipelines, instructions, and common includes."""
    manifest = load_manifest(preset)
    return {
        "skills": set(manifest.get("skills", [])),
        "hooks": set(manifest.get("hooks", [])),
        "pipelines": set(manifest.get("pipelines", [])),
        "external": set(manifest.get("external", [])),
        "instructions": list(manifest.get("instructions", [])),
        "common": list(manifest.get("common", [])),
    }


def resolve_dependencies(components: dict) -> dict:
    """Add dependencies (e.g., workspace pipeline needs link-proxy)."""
    if "workspace" in components["pipelines"]:
        components["hooks"].add("link-proxy")
    return components


def update_config(target: Path, preset: str, knowledge_base: Path | None = None):
    """Create or update .claude/agentic-kit.json with paths."""
    config_path = target / ".claude" / "agentic-kit.json"

    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        # Bootstrap from preset template if available
        template_path = PRESETS_DIR / preset / "agentic-kit.template.json"
        config = json.loads(template_path.read_text()) if template_path.exists() else {}

    # Always update agentic_kit path (detected from this script's location)
    config["agentic_kit"] = str(REPO_ROOT)

    # Update knowledge_base if provided
    if knowledge_base:
        config["knowledge_base"] = str(knowledge_base.expanduser().resolve())

    config_path.write_text(json.dumps(config, indent=2))
    return config


def install(preset: str, target: Path, knowledge_base: Path | None = None):
    """Main installation logic."""
    console.print(f"[bold]Installing preset:[/bold] {preset}")

    components = collect_components(preset)
    components = resolve_dependencies(components)

    target_claude = target / ".claude"
    target_claude.mkdir(parents=True, exist_ok=True)

    # Merge settings from preset with existing settings
    settings = merge_settings(preset, target)

    # Add hook configurations from hooks.json files
    for hook in components["hooks"]:
        hook_dir = (target_claude / "hooks" / hook).resolve()
        hook_config = load_hook_config(hook, hook_dir)
        merge_hooks(settings["hooks"], hook_config)

    (target_claude / "settings.json").write_text(json.dumps(settings, indent=2))
    console.print("  [green]✓[/green] .claude/settings.json")

    # Create/update agentic-kit.json with paths
    config = update_config(target, preset, knowledge_base)
    console.print("  [green]✓[/green] .claude/agentic-kit.json")
    console.print(f"      agentic_kit: {config.get('agentic_kit', 'not set')}")
    if config.get("knowledge_base"):
        console.print(f"      knowledge_base: {config['knowledge_base']}")

    # Process and write .claude/CLAUDE.md (preset instructions with includes resolved)
    # Root CLAUDE.md is left for user's project-specific instructions
    target_claude_md = target_claude / "CLAUDE.md"
    src = PRESETS_DIR / preset / "claude.md"
    if src.exists():
        content = src.read_text()

        # Validate common file dependencies (from both template includes and manifest)
        template_commons = extract_common_names_from_template(content)
        all_commons = list(dict.fromkeys(template_commons + components["common"]))
        dep_errors = validate_common_dependencies(all_commons, components["skills"])
        if dep_errors:
            for e in dep_errors:
                console.print(f"  [red]✗[/red] {e}")
            console.print(
                "[red]Installation failed: common file dependencies not satisfied[/red]"
            )
            raise SystemExit(1)

        processed = process_includes(content)  # Process first, may raise

        # Append preset-specific instructions from manifest
        if components["instructions"]:
            instructions_dir = PRESETS_DIR / preset / "instructions"
            sections = []
            for name in components["instructions"]:
                path = instructions_dir / f"{name}.md"
                if path.exists():
                    sections.append(strip_frontmatter(path.read_text()).strip())
                else:
                    raise FileNotFoundError(
                        f"Instruction not found: {preset}/instructions/{name}.md"
                    )
            if sections:
                processed = processed.rstrip() + "\n\n" + "\n\n".join(sections) + "\n"

        # Append common sections from manifest
        if components["common"]:
            sections = []
            for name in components["common"]:
                path = COMMON_DIR / f"{name}.md"
                if path.exists():
                    _, body = parse_frontmatter(path.read_text())
                    sections.append(body.strip())
                else:
                    raise FileNotFoundError(f"Common file not found: {name}.md")
            if sections:
                processed = processed.rstrip() + "\n\n" + "\n\n".join(sections) + "\n"

        # Only delete after successful processing
        if target_claude_md.exists() or target_claude_md.is_symlink():
            target_claude_md.unlink()
        target_claude_md.write_text(processed)
        console.print("  [green]✓[/green] .claude/CLAUDE.md (includes processed)")

    # Symlink templates folder
    templates_src = PRESETS_DIR / preset / "templates"
    if templates_src.exists():
        templates_dst = target_claude / "templates"
        if templates_dst.exists() or templates_dst.is_symlink():
            if templates_dst.is_symlink():
                templates_dst.unlink()
            else:
                shutil.rmtree(templates_dst)
        templates_dst.symlink_to(templates_src)
        console.print("  [green]✓[/green] .claude/templates/")

    # Copy workspace template if preset has one and target doesn't exist
    workspace_template = PRESETS_DIR / preset / "workspace_template.yaml"
    workspace_target = target / "WORKSPACE.yaml"
    if workspace_template.exists() and not workspace_target.exists():
        shutil.copy(workspace_template, workspace_target)
        console.print("  [green]✓[/green] WORKSPACE.yaml (from template)")

    # Sync symlinks — adds missing, removes stale, updates outdated
    sync_symlinks(SKILLS_DIR, target_claude / "skills", components["skills"], "Skill")
    sync_symlinks(HOOKS_DIR, target_claude / "hooks", components["hooks"], "Hook")
    if components["pipelines"]:
        sync_symlinks(
            PIPELINES_DIR, target / "pipelines", components["pipelines"], "Pipeline"
        )

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
    args = parser.parse_args()

    if args.list:
        list_presets()
        return

    if args.preset:
        preset = args.preset
    else:
        # Interactive selection
        available = sorted([p.name for p in PRESETS_DIR.iterdir() if p.is_dir()])
        console.print("[bold]Available presets:[/bold]")
        for i, p in enumerate(available, 1):
            manifest = load_manifest(p)
            desc = manifest.get("description", "")
            console.print(f"  {i}. [cyan]{p}[/cyan]: {desc}")
        selection = Prompt.ask("\nSelect preset (number)")
        idx = int(selection.strip()) - 1
        if 0 <= idx < len(available):
            preset = available[idx]
        else:
            console.print("[red]Invalid selection[/red]")
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
