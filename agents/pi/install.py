import json
import shutil

from lib.install_types import InstallContext
from lib.install_utils import (
    merge_hooks,
    parse_frontmatter,
    strip_frontmatter,
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
    # Remove permissions and modelRouter — Pi doesn't use them
    settings.pop("permissions", None)
    settings.pop("modelRouter", None)
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


def install_disguise_template(ctx: InstallContext, console=None) -> None:
    """Copy disguise.template.yaml to the workspace root as disguise.yaml if it doesn't exist."""
    workspace_root = ctx.project_dir.parent
    disguise_dest = workspace_root / "disguise.yaml"
    if disguise_dest.exists():
        return
    template = ctx.agent_dir / "disguise.template.yaml"
    if not template.exists():
        return
    shutil.copy2(template, disguise_dest)
    if console:
        console.print(f"  Created disguise.yaml template at {disguise_dest}")


def write_system_prompt(ctx: InstallContext, console=None) -> None:
    """Generate .pi/prompt.md from system_prompt common + local files."""
    parts: list[str] = []

    # Common fragments first
    if ctx.common:
        common_dir = ctx.repo_root / "common"
        for name in ctx.common:
            path = common_dir / f"{name}.md"
            if not path.exists():
                raise FileNotFoundError(f"Common file not found: {name}.md")
            _, body = parse_frontmatter(path.read_text())
            parts.append(body.strip())

    # Then local files from the flavor directory
    local_files = ctx.system_prompt_local if ctx.system_prompt_local else []
    for local_file in local_files:
        local_path = ctx.agent_dir / local_file
        if not local_path.exists():
            raise FileNotFoundError(
                f"Local system_prompt file not found: {local_file} "
                f"(looked in {ctx.agent_dir})"
            )
        content = strip_frontmatter(local_path.read_text()).strip()
        if content:
            parts.append(content)

    # Profile instructions
    if ctx.instructions:
        for name in ctx.instructions:
            path = ctx.profile_dir / "instructions" / f"{name}.md"
            if not path.exists():
                path = ctx.agent_dir / "instructions" / f"{name}.md"
            if path.exists():
                parts.append(strip_frontmatter(path.read_text()).strip())

    if parts:
        prompt_path = ctx.project_dir / "prompt.md"
        prompt_path.write_text("\n\n".join(parts) + "\n")
        if console:
            console.print(f"  Generated prompt.md ({len(parts)} sections)")


def install(ctx: InstallContext, console=None) -> None:
    ctx.project_dir.mkdir(parents=True, exist_ok=True)
    validate_required_extensions(ctx)
    install_disguise_template(ctx, console=console)
    write_system_prompt(ctx, console=console)
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
