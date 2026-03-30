import json

from lib.install_types import InstallContext
from lib.install_utils import (
    merge_hooks,
    sync_symlinks,
    update_managed_config,
    write_json,
)

AGENT_DIRNAME = ".pi"
DEFAULT_SETTINGS = {
    "defaultProvider": "nestor",
    "defaultModel": "tgpt/qwen35-397b-a17b-fp8",
    "defaultThinkingLevel": "medium",
}
DEFAULT_EXTENSIONS = {"nestor-provider", "permission-gate", "background-tasks"}


def validate_required_extensions(ctx: InstallContext) -> None:
    extensions_root = ctx.repo_root / "agents" / "pi" / "extensions"
    missing = sorted(
        name for name in DEFAULT_EXTENSIONS if not (extensions_root / name).exists()
    )
    if missing:
        raise FileNotFoundError(
            "Missing required Pi bundled extensions: " + ", ".join(missing)
        )


def install_hooks(ctx: InstallContext, console=None) -> None:
    """Generate .pi/hooks.json with absolute paths to hook scripts.

    Unlike Claude Code, we don't symlink hooks into .pi/hooks/ because Pi
    uses that directory for its own purposes. Instead, we resolve each hook
    command to the absolute path of its script in the agentic-kit repo.
    """
    if not ctx.hooks:
        return

    hooks_root = ctx.repo_root / "hooks"
    merged: dict = {}

    for hook_name in ctx.hooks:
        hooks_json_path = hooks_root / hook_name / "hooks.json"
        if not hooks_json_path.exists():
            continue

        # Find the hook script (hook.py or hook.sh)
        hook_dir = hooks_root / hook_name
        hook_script = None
        for candidate in ["hook.py", "hook.sh"]:
            if (hook_dir / candidate).exists():
                hook_script = str(hook_dir / candidate)
                break

        if not hook_script:
            continue

        # Build command: uv run for Python, direct for shell
        if hook_script.endswith(".py"):
            command = f"uv run {hook_script}"
        else:
            command = hook_script

        # Load hooks.json and replace the bare command name with the full path
        raw = hooks_json_path.read_text()
        config = json.loads(raw)

        for event_hooks in config.values():
            for matcher_group in event_hooks:
                for hook in matcher_group.get("hooks", []):
                    hook["command"] = command

        merge_hooks(merged, config)

    if merged:
        write_json(ctx.project_dir / "hooks.json", merged)


def install(ctx: InstallContext, console=None) -> None:
    ctx.project_dir.mkdir(parents=True, exist_ok=True)
    validate_required_extensions(ctx)
    sync_symlinks(
        ctx.repo_root / "skills",
        ctx.project_dir / "skills",
        set(ctx.skills),
        "Skill",
        console=console,
    )
    sync_symlinks(
        ctx.repo_root / "agents" / "pi" / "extensions",
        ctx.project_dir / "extensions",
        DEFAULT_EXTENSIONS,
        "Extension",
        console=console,
    )
    missing_links = sorted(
        name
        for name in DEFAULT_EXTENSIONS
        if not (ctx.project_dir / "extensions" / name).is_symlink()
    )
    if missing_links:
        raise FileNotFoundError(
            "Failed to install required Pi bundled extensions: "
            + ", ".join(missing_links)
        )
    install_hooks(ctx, console=console)
    write_json(ctx.project_dir / "settings.json", DEFAULT_SETTINGS)
    update_managed_config(ctx.project_dir / "agentic-kit.json", ctx)
