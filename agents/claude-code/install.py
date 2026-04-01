import shutil
from pathlib import Path

from lib.install_types import InstallContext
from lib.install_utils import (
    extract_common_names_from_template,
    load_hook_config,
    load_json,
    merge_hooks,
    parse_frontmatter,
    process_includes,
    strip_frontmatter,
    sync_symlinks,
    update_managed_config,
    write_json,
)
from lib.install_utils import (
    validate_common_dependencies as validate_common_dependencies_in_dir,
)

AGENT_DIRNAME = ".claude"


def load_existing_settings(project_dir: Path) -> dict:
    return load_json(project_dir / "settings.json", {"hooks": {}, "permissions": {}})


def merge_permissions(existing: dict, new: dict):
    for key in ["allow", "deny"]:
        if key not in new:
            continue
        existing.setdefault(key, [])
        for perm in new[key]:
            if perm not in existing[key]:
                existing[key].append(perm)


def update_config(ctx: InstallContext) -> dict:
    config_path = ctx.project_dir / "agentic-kit.json"
    template_path = ctx.profile_dir / "agentic-kit.template.json"
    return update_managed_config(config_path, ctx, bootstrap_path=template_path)


def validate_common_dependencies(
    ctx: InstallContext, common_names: list[str]
) -> list[str]:
    return validate_common_dependencies_in_dir(
        common_names,
        set(ctx.skills),
        ctx.repo_root / "common",
    )


def write_claude_md(ctx: InstallContext):
    # Build system prompt from local files
    local_files = ctx.system_prompt_local if ctx.system_prompt_local else ["prompt.md"]

    # Read first local file as the base template (may contain {{include:}} directives)
    src = ctx.agent_dir / local_files[0]
    if not src.exists():
        return

    content = src.read_text()
    template_commons = extract_common_names_from_template(content)
    all_commons = list(dict.fromkeys(template_commons + list(ctx.common)))
    dep_errors = validate_common_dependencies(ctx, all_commons)
    if dep_errors:
        raise ValueError(
            "Common file dependencies not satisfied: " + "; ".join(dep_errors)
        )

    processed = process_includes(content, ctx.repo_root)

    # Append additional local files (beyond the first)
    for local_file in local_files[1:]:
        local_path = ctx.agent_dir / local_file
        if not local_path.exists():
            raise FileNotFoundError(f"Local system_prompt file not found: {local_file}")
        local_content = strip_frontmatter(local_path.read_text()).strip()
        if local_content:
            processed = processed.rstrip() + "\n\n" + local_content + "\n"

    # Inject profile instructions
    if ctx.instructions:
        sections = []
        for name in ctx.instructions:
            # Look in profile's instructions/ first, then agent's
            path = ctx.profile_dir / "instructions" / f"{name}.md"
            if not path.exists():
                path = ctx.agent_dir / "instructions" / f"{name}.md"
            if not path.exists():
                raise FileNotFoundError(
                    f"Instruction not found: {name}.md "
                    f"(checked {ctx.profile_dir / 'instructions'} and {ctx.agent_dir / 'instructions'})"
                )
            sections.append(strip_frontmatter(path.read_text()).strip())
        if sections:
            processed = processed.rstrip() + "\n\n" + "\n\n".join(sections) + "\n"

    # Append common fragments
    if ctx.common:
        common_dir = ctx.repo_root / "common"
        sections = []
        for name in ctx.common:
            path = common_dir / f"{name}.md"
            if not path.exists():
                raise FileNotFoundError(f"Common file not found: {name}.md")
            _, body = parse_frontmatter(path.read_text())
            sections.append(body.strip())
        if sections:
            processed = processed.rstrip() + "\n\n" + "\n\n".join(sections) + "\n"

    target_claude_md = ctx.project_dir / "CLAUDE.md"
    if target_claude_md.exists() or target_claude_md.is_symlink():
        target_claude_md.unlink()
    target_claude_md.write_text(processed)


def sync_templates(ctx: InstallContext):
    # Check profile for templates first, then agent
    templates_src = ctx.profile_dir / "templates"
    if not templates_src.exists():
        templates_src = ctx.agent_dir / "templates"

    templates_dst = ctx.project_dir / "templates"
    if not templates_src.exists():
        # No templates source — clean up any stale symlink
        if templates_dst.is_symlink():
            templates_dst.unlink()
        return

    if templates_dst.exists() or templates_dst.is_symlink():
        if templates_dst.is_symlink():
            templates_dst.unlink()
        else:
            shutil.rmtree(templates_dst)
    templates_dst.symlink_to(templates_src)


def sync_workspace_template(ctx: InstallContext):
    # Check profile for workspace template
    workspace_template = ctx.profile_dir / "workspace_template.yaml"
    workspace_target = ctx.target_dir / "WORKSPACE.yaml"
    if workspace_template.exists() and not workspace_target.exists():
        shutil.copy(workspace_template, workspace_target)


def build_hook_settings(ctx: InstallContext) -> dict:
    settings = load_existing_settings(ctx.project_dir)
    settings["hooks"] = {}

    # Merge permissions from ctx.settings (pre-merged profile + agent)
    if ctx.settings.get("permissions"):
        settings.setdefault("permissions", {})
        merge_permissions(settings["permissions"], ctx.settings["permissions"])

    # Merge hook configs from hook directories
    hooks_root = ctx.repo_root / "hooks"
    for hook in ctx.hooks:
        hook_dir = (ctx.project_dir / "hooks" / hook).resolve()
        hook_config = load_hook_config(hook, hook_dir, hooks_root)
        merge_hooks(settings["hooks"], hook_config)
    return settings


def install(ctx: InstallContext, console=None) -> None:
    ctx.project_dir.mkdir(parents=True, exist_ok=True)

    settings = build_hook_settings(ctx)
    write_json(ctx.project_dir / "settings.json", settings)

    update_config(ctx)
    write_claude_md(ctx)
    sync_templates(ctx)
    sync_workspace_template(ctx)

    sync_symlinks(
        ctx.repo_root / "skills",
        ctx.project_dir / "skills",
        set(ctx.skills),
        "Skill",
        console=console,
    )
    sync_symlinks(
        ctx.repo_root / "hooks",
        ctx.project_dir / "hooks",
        set(ctx.hooks),
        "Hook",
        console=console,
    )
    if ctx.pipelines:
        sync_symlinks(
            ctx.repo_root / "pipelines",
            ctx.target_dir / "pipelines",
            set(ctx.pipelines),
            "Pipeline",
            console=console,
        )
