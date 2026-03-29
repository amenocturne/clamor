from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Optional

import yaml

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


def process_includes(content: str, repo_root: Path) -> str:
    """Process {{include:path}} directives, replacing them with file contents."""

    def replace_include(match):
        include_path = match.group(1)
        full_path = repo_root / include_path
        if full_path.exists():
            return strip_frontmatter(full_path.read_text()).strip()
        raise FileNotFoundError(f"Include not found: {include_path}")

    return re.sub(INCLUDE_PATTERN, replace_include, content)


def extract_common_names_from_template(content: str) -> list[str]:
    """Extract common file names from {{include:common/...}} directives."""
    names = []
    for match in re.finditer(INCLUDE_PATTERN, content):
        path = match.group(1)
        if path.startswith("common/"):
            names.append(path.removeprefix("common/").removesuffix(".md"))
    return names


def validate_common_dependencies(
    common_names: list[str], available_skills: set[str], common_dir: Path
) -> list[str]:
    """Check that common files' required skills are present in the preset."""
    errors = []
    for name in common_names:
        path = common_dir / f"{name}.md"
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


def load_hook_config(hook_name: str, hook_dir: Path, hooks_root: Path) -> dict:
    """Load hooks.json from a hook directory and resolve {hook_dir} placeholders."""
    hooks_json = hooks_root / hook_name / "hooks.json"
    if not hooks_json.exists():
        return {}

    content = hooks_json.read_text().replace("{hook_dir}", str(hook_dir))
    return json.loads(content)


def load_json(path: Path, default: Optional[dict] = None) -> dict:
    """Load JSON from path or return a copy of default."""
    if path.exists():
        return json.loads(path.read_text())
    return deepcopy(default) if default is not None else {}


def write_json(path: Path, data: dict):
    """Write JSON with a stable, readable format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def normalize_manifest_list(value) -> list[str]:
    """Return a normalized string list for manifest keys."""
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    raise TypeError(f"Expected list or null, got {type(value).__name__}")


def merge_dicts(base: dict, override: dict) -> dict:
    """Deep-merge override into base and return the merged dict."""
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def build_managed_install_state(ctx) -> dict:
    """Build conservative install metadata for agent-managed config files."""
    managed = {
        "preset": ctx.preset_name,
        "target_dir": str(ctx.target_dir.resolve()),
        "project_dir": str(ctx.project_dir.resolve()),
        "agents": list(ctx.all_agents),
        "project_dirs": {
            name: str(path.resolve()) for name, path in sorted(ctx.project_dirs.items())
        },
    }
    if ctx.install_state_path is not None:
        managed["install_state_path"] = str(ctx.install_state_path.resolve())
    return managed


def update_managed_config(
    path: Path,
    ctx,
    *,
    bootstrap_path: Optional[Path] = None,
    extra: Optional[dict] = None,
) -> dict:
    """Update an agent-managed config file without clobbering user settings."""
    config = load_json(path)
    if not config and bootstrap_path is not None and bootstrap_path.exists():
        config = load_json(bootstrap_path)

    config["agentic_kit"] = str(ctx.repo_root)
    if ctx.knowledge_base:
        config["knowledge_base"] = str(ctx.knowledge_base.expanduser().resolve())
    if extra:
        config = merge_dicts(config, extra)

    managed = config.get("managed")
    if not isinstance(managed, dict):
        managed = {}
    managed.update(build_managed_install_state(ctx))
    config["managed"] = managed

    write_json(path, config)
    return config


def get_hook_key(hook_entry: dict) -> Optional[str]:
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

        existing_by_key = {}
        for i, hook_entry in enumerate(base[hook_type]):
            key = get_hook_key(hook_entry)
            if key:
                existing_by_key[key] = i

        for new_hook in new_hooks:
            key = get_hook_key(new_hook)
            if key and key in existing_by_key:
                base[hook_type][existing_by_key[key]] = new_hook
            else:
                base[hook_type].append(new_hook)
                if key:
                    existing_by_key[key] = len(base[hook_type]) - 1

    return base


def sync_symlinks(
    source_dir: Path,
    target_dir: Path,
    wanted: set[str],
    label: str,
    console=None,
):
    """Sync symlinks in target_dir to match wanted set."""
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
            if console is not None:
                console.print(f"  [yellow]−[/yellow] {label}: {entry.name} (removed)")
        elif link_target != source_dir / entry.name:
            entry.unlink()
            entry.symlink_to(source_dir / entry.name)
            if console is not None:
                console.print(f"  [blue]↻[/blue] {label}: {entry.name} (updated)")

    for name in sorted(wanted):
        src = source_dir / name
        dst = target_dir / name
        if src.exists() and not dst.exists():
            dst.symlink_to(src)
            if console is not None:
                console.print(f"  [green]✓[/green] {label}: {name}")


def load_registry(registry_path: Path) -> list[dict]:
    """Read installations.yaml and return list of entries. Empty list if missing."""
    if not registry_path.exists():
        return []
    content = registry_path.read_text()
    entries = yaml.safe_load(content)
    return entries if isinstance(entries, list) else []


def save_registry(entries: list[dict], registry_path: Path):
    """Write list of installation entries to installations.yaml."""
    registry_path.write_text(
        yaml.dump(entries, default_flow_style=False, sort_keys=False)
    )
