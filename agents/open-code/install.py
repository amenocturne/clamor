from lib.install_types import InstallContext
from lib.install_utils import sync_symlinks, update_managed_config

AGENT_DIRNAME = ".opencode"


def update_config(ctx: InstallContext) -> dict:
    return update_managed_config(ctx.project_dir / "agentic-kit.json", ctx)


def install(ctx: InstallContext, console=None) -> None:
    ctx.project_dir.mkdir(parents=True, exist_ok=True)
    sync_symlinks(
        ctx.repo_root / "skills",
        ctx.project_dir / "skills",
        set(ctx.skills),
        "Skill",
        console=console,
    )
    update_config(ctx)
