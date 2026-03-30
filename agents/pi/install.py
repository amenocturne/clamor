from lib.install_types import InstallContext
from lib.install_utils import (
    load_hook_config,
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
    """Symlink hooks and generate merged .pi/hooks.json for permission-gate."""
    if not ctx.hooks:
        return

    # Symlink hook directories
    sync_symlinks(
        ctx.repo_root / "hooks",
        ctx.project_dir / "hooks",
        set(ctx.hooks),
        "Hook",
        console=console,
    )

    # Merge all hook configs into a single hooks.json
    merged: dict = {}
    for hook_name in ctx.hooks:
        # Resolve hook_dir to the symlinked location so paths work at runtime
        hook_dir = ctx.project_dir / "hooks" / hook_name
        config = load_hook_config(hook_name, hook_dir, ctx.repo_root / "hooks")
        if config:
            merge_hooks(merged, config)

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
