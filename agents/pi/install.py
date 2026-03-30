import json
import shutil
from pathlib import Path

from lib.install_types import InstallContext
from lib.install_utils import (
    merge_hooks,
    sync_symlinks,
    update_managed_config,
    write_json,
)

AGENT_DIRNAME = ".pi"


def get_extensions(ctx: InstallContext) -> set[str]:
    return set(ctx.extensions)


def get_settings(ctx: InstallContext) -> dict:
    # Settings come pre-merged from profile × agent manifests
    settings = dict(ctx.settings)
    # Remove permissions — Pi doesn't use them
    settings.pop("permissions", None)
    # Ensure a default thinking level
    settings.setdefault("defaultThinkingLevel", "medium")
    return settings


def validate_required_extensions(ctx: InstallContext) -> None:
    extensions_root = ctx.repo_root / "agents" / "pi" / "extensions"
    wanted = get_extensions(ctx)
    missing = sorted(name for name in wanted if not (extensions_root / name).exists())
    if missing:
        raise FileNotFoundError(
            "Missing required Pi bundled extensions: " + ", ".join(missing)
        )


def install_hooks(ctx: InstallContext, console=None) -> None:
    """Generate hooks.json with absolute paths to hook scripts."""
    if not ctx.hooks:
        return

    hooks_root = ctx.repo_root / "hooks"
    merged: dict = {}

    for hook_name in ctx.hooks:
        hooks_json_path = hooks_root / hook_name / "hooks.json"
        if not hooks_json_path.exists():
            continue

        hook_dir = hooks_root / hook_name
        hook_script = None
        for candidate in ["hook.py", "hook.sh"]:
            if (hook_dir / candidate).exists():
                hook_script = str(hook_dir / candidate)
                break

        if not hook_script:
            continue

        if hook_script.endswith(".py"):
            command = f"uv run {hook_script}"
        else:
            command = hook_script

        raw = hooks_json_path.read_text()
        config = json.loads(raw)

        for event_hooks in config.values():
            for matcher_group in event_hooks:
                for hook in matcher_group.get("hooks", []):
                    hook["command"] = command

        merge_hooks(merged, config)

    if merged:
        write_json(ctx.project_dir / "hooks.json", merged)


def install_teams_template(ctx: InstallContext, console=None) -> None:
    """Copy teams.template.yaml to the workspace root as teams.yaml if it doesn't exist."""
    # target_dir is the workspace root (parent of .pi/ project_dir)
    workspace_root = ctx.project_dir.parent
    teams_dest = workspace_root / "teams.yaml"
    if teams_dest.exists():
        return
    template = ctx.repo_root / "agents" / "pi" / "teams.template.yaml"
    if not template.exists():
        return
    shutil.copy2(template, teams_dest)
    if console:
        console.print(f"  Created teams.yaml template at {teams_dest}")


def install(ctx: InstallContext, console=None) -> None:
    ctx.project_dir.mkdir(parents=True, exist_ok=True)
    validate_required_extensions(ctx)
    install_teams_template(ctx, console=console)
    wanted = get_extensions(ctx)
    sync_symlinks(
        ctx.repo_root / "skills",
        ctx.project_dir / "skills",
        set(ctx.skills),
        "Skill",
        console=console,
    )
    if wanted:
        sync_symlinks(
            ctx.repo_root / "agents" / "pi" / "extensions",
            ctx.project_dir / "extensions",
            wanted,
            "Extension",
            console=console,
        )
        missing_links = sorted(
            name
            for name in wanted
            if not (ctx.project_dir / "extensions" / name).is_symlink()
        )
        if missing_links:
            raise FileNotFoundError(
                "Failed to install required Pi bundled extensions: "
                + ", ".join(missing_links)
            )
    install_hooks(ctx, console=console)
    write_json(ctx.project_dir / "settings.json", get_settings(ctx))
    update_managed_config(ctx.project_dir / "agentic-kit.json", ctx)
