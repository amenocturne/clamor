from lib.install_types import InstallContext
from lib.install_utils import sync_symlinks, update_managed_config, write_json

AGENT_DIRNAME = ".pi"
DEFAULT_SETTINGS = {
    "defaultProvider": "nestor",
    "defaultModel": "tgpt/qwen35-397b-a17b-fp8",
    "defaultThinkingLevel": "medium",
}
DEFAULT_EXTENSIONS = {"nestor-provider"}


def validate_required_extensions(ctx: InstallContext) -> None:
    extensions_root = ctx.repo_root / "agents" / "pi" / "extensions"
    missing = sorted(
        name for name in DEFAULT_EXTENSIONS if not (extensions_root / name).exists()
    )
    if missing:
        raise FileNotFoundError(
            "Missing required Pi bundled extensions: " + ", ".join(missing)
        )


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
    write_json(ctx.project_dir / "settings.json", DEFAULT_SETTINGS)
    update_managed_config(ctx.project_dir / "agentic-kit.json", ctx)
