"""Tests for install.py — the core installer (v2: profile × agent architecture)."""

import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Mock yaml and rich *before* importing install so we don't need pyyaml/rich
# installed in the test environment.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def _mock_safe_load(text: str):
    """Minimal yaml.safe_load replacement for tests.

    Handles:
    - Empty/whitespace-only strings -> None  (matches real yaml.safe_load)
    - JSON content (produced by make_profile/make_agent via json.dumps)
    - Simple "key:\\n" YAML where bare keys have null values
    """
    if text is None or text.strip() == "":
        return None
    # Try JSON first (our test helpers write manifests as JSON)
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: very simple single-level YAML parser for lines like "key: value"
    # and bare "key:" (value is None).
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            val = val.strip()
            if val == "" or val.lower() in ("null", "~"):
                result[key.strip()] = None
            else:
                result[key.strip()] = val
    return result if result else text


def _mock_dump(data, **kwargs):
    """Minimal yaml.dump replacement — just returns JSON."""
    return json.dumps(data)


# Build the mock yaml module
_mock_yaml = ModuleType("yaml")
_mock_yaml.safe_load = _mock_safe_load
_mock_yaml.dump = _mock_dump

# Build mock rich modules (install.py uses Console and Prompt from rich)
_mock_rich = ModuleType("rich")
_mock_rich_console = ModuleType("rich.console")
_mock_rich_prompt = ModuleType("rich.prompt")

_MockConsole = MagicMock()
_MockPrompt = MagicMock()
_mock_rich_console.Console = _MockConsole
_mock_rich_prompt.Prompt = _MockPrompt
_mock_rich.console = _mock_rich_console
_mock_rich.prompt = _mock_rich_prompt

# Inject mocks before importing install (force-set to ensure our custom
# _mock_safe_load is used even if another test already set a yaml mock).
sys.modules["yaml"] = _mock_yaml
sys.modules.setdefault("rich", _mock_rich)
sys.modules.setdefault("rich.console", _mock_rich_console)
sys.modules.setdefault("rich.prompt", _mock_rich_prompt)

import install  # noqa: E402
from lib.install_utils import merge_hooks, merge_manifests  # noqa: E402

CLAUDE_INSTALLER = install.load_agent_installer("claude-code")
OPEN_CODE_INSTALLER = install.load_agent_installer("open-code")
PI_INSTALLER = install.load_agent_installer("pi")


# ---------------------------------------------------------------------------
# Helpers to build fake repo layouts inside tmp_path
# ---------------------------------------------------------------------------


def make_profile(
    profiles_dir: Path,
    name: str,
    manifest: dict | None = None,
):
    """Create a profile directory with optional manifest."""
    d = profiles_dir / name
    d.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (d / "manifest.yaml").write_text(json.dumps(manifest))


def make_agent(
    agents_dir: Path,
    name: str,
    manifest: dict | None = None,
    prompt_md: str | None = None,
):
    """Create an agent directory with optional manifest and prompt.md."""
    d = agents_dir / name
    d.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (d / "manifest.yaml").write_text(json.dumps(manifest))
    if prompt_md is not None:
        (d / "prompt.md").write_text(prompt_md)


def make_skill(skills_dir: Path, name: str):
    """Create a skill directory with a dummy file."""
    d = skills_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "skill.md").write_text(f"Skill: {name}")


def make_hook(hooks_dir: Path, name: str, hooks_json: dict | None = None):
    """Create a hook directory with optional hooks.json."""
    d = hooks_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "hook.sh").write_text(f"#!/bin/bash\n# Hook: {name}")
    if hooks_json is not None:
        (d / "hooks.json").write_text(json.dumps(hooks_json))


def make_pipeline(pipelines_dir: Path, name: str):
    """Create a pipeline directory with a dummy file."""
    d = pipelines_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "pipeline.py").write_text(f"# Pipeline: {name}")


def make_common(
    common_dir: Path, name: str, content: str, requires: dict | None = None
):
    """Create a common file with optional frontmatter.

    Uses JSON in the frontmatter block so the mock yaml parser can handle it.
    """
    if requires:
        frontmatter_data = json.dumps({"required_skills": requires.get("skills", [])})
        content = f"---\n{frontmatter_data}\n---\n\n{content}"
    (common_dir / f"{name}.md").write_text(content)


def make_instruction(base_dir: Path, parent: str, name: str, content: str):
    """Create an instruction file under <base_dir>/<parent>/instructions/."""
    d = base_dir / parent / "instructions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(content)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_repo(tmp_path):
    """Build a fake repo layout and patch install module globals to use it."""
    profiles_dir = tmp_path / "profiles"
    agents_dir = tmp_path / "agents"
    skills_dir = tmp_path / "skills"
    hooks_dir = tmp_path / "hooks"
    pipelines_dir = tmp_path / "pipelines"
    common_dir = tmp_path / "common"
    profiles_dir.mkdir()
    agents_dir.mkdir()
    skills_dir.mkdir()
    hooks_dir.mkdir()
    pipelines_dir.mkdir()
    common_dir.mkdir()

    # Create the pi extensions directory structure (needed for pi installer)
    (agents_dir / "pi" / "extensions" / "permission-gate").mkdir(parents=True)
    (agents_dir / "pi" / "extensions" / "background-tasks").mkdir(parents=True)

    with (
        patch.object(install, "REPO_ROOT", tmp_path),
        patch.object(install, "PROFILES_DIR", profiles_dir),
        patch.object(install, "AGENTS_DIR", agents_dir),
        patch.object(install, "SKILLS_DIR", skills_dir),
        patch.object(install, "HOOKS_DIR", hooks_dir),
        patch.object(install, "PIPELINES_DIR", pipelines_dir),
        patch.object(install, "COMMON_DIR", common_dir),
        patch.object(install, "REGISTRY_PATH", tmp_path / "installations.yaml"),
        patch.object(
            install,
            "load_agent_installer",
            side_effect=lambda runtime: {
                "claude-code": CLAUDE_INSTALLER,
                "open-code": OPEN_CODE_INSTALLER,
                "pi": PI_INSTALLER,
            }[runtime],
        ),
    ):
        yield {
            "root": tmp_path,
            "profiles": profiles_dir,
            "agents": agents_dir,
            "skills": skills_dir,
            "hooks": hooks_dir,
            "pipelines": pipelines_dir,
            "common": common_dir,
        }


# ===================================================================
# load_profile_manifest / load_agent_manifest
# ===================================================================


class TestLoadManifests:
    """Test loading manifests for profiles and agents."""

    def test_loads_valid_profile_manifest(self, fake_repo):
        manifest = {
            "description": "Test profile",
            "common": ["git-personal"],
            "hooks": ["worktree"],
        }
        make_profile(fake_repo["profiles"], "test", manifest=manifest)
        result = install.load_profile_manifest("test")
        assert result["description"] == "Test profile"
        assert result["common"] == ["git-personal"]
        assert result["hooks"] == ["worktree"]

    def test_missing_profile_raises(self, fake_repo):
        with pytest.raises(FileNotFoundError):
            install.load_profile_manifest("nonexistent")

    def test_empty_profile_manifest(self, fake_repo):
        d = fake_repo["profiles"] / "empty"
        d.mkdir()
        (d / "manifest.yaml").write_text("")
        result = install.load_profile_manifest("empty")
        assert result == {}

    def test_loads_valid_agent_manifest(self, fake_repo):
        manifest = {
            "description": "Claude Code agent",
            "runtime": "claude-code",
            "target": ".claude",
            "skills": ["spec"],
        }
        make_agent(fake_repo["agents"], "test-agent", manifest=manifest)
        result = install.load_agent_manifest("test-agent")
        assert result["runtime"] == "claude-code"
        assert result["target"] == ".claude"
        assert result["skills"] == ["spec"]

    def test_missing_agent_raises(self, fake_repo):
        with pytest.raises(FileNotFoundError):
            install.load_agent_manifest("nonexistent")

    def test_profile_with_only_description(self, fake_repo):
        make_profile(
            fake_repo["profiles"],
            "minimal",
            manifest={"description": "Minimal"},
        )
        result = install.load_profile_manifest("minimal")
        assert result["description"] == "Minimal"
        assert result.get("skills") is None


# ===================================================================
# load_hook_config
# ===================================================================


class TestLoadHookConfig:
    """Test loading hooks.json with {hook_dir} resolution."""

    def test_loads_and_resolves_hook_dir(self, fake_repo):
        hooks_json = {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "{hook_dir}/hook.sh stop",
                            "timeout": 5,
                        }
                    ]
                }
            ]
        }
        make_hook(fake_repo["hooks"], "my-hook", hooks_json=hooks_json)
        target_hook_dir = Path("/project/hooks/my-hook")
        result = install.load_hook_config("my-hook", target_hook_dir)
        assert (
            result["Stop"][0]["hooks"][0]["command"]
            == "/project/hooks/my-hook/hook.sh stop"
        )

    def test_multiple_placeholders_resolved(self, fake_repo):
        hooks_json = {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "{hook_dir}/pre.sh",
                        }
                    ]
                }
            ],
            "PostToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "{hook_dir}/post.sh",
                        }
                    ]
                }
            ],
        }
        make_hook(fake_repo["hooks"], "multi", hooks_json=hooks_json)
        target = Path("/t/hooks/multi")
        result = install.load_hook_config("multi", target)
        assert result["PreToolUse"][0]["hooks"][0]["command"] == "/t/hooks/multi/pre.sh"
        assert (
            result["PostToolUse"][0]["hooks"][0]["command"] == "/t/hooks/multi/post.sh"
        )

    def test_missing_hooks_json_returns_empty(self, fake_repo):
        d = fake_repo["hooks"] / "no-json"
        d.mkdir()
        result = install.load_hook_config("no-json", Path("/target/hooks/no-json"))
        assert result == {}

    def test_missing_hook_dir_returns_empty(self, fake_repo):
        result = install.load_hook_config("does-not-exist", Path("/target/hooks/x"))
        assert result == {}


# ===================================================================
# merge_hooks (now in lib.install_utils)
# ===================================================================


class TestMergeHooks:
    """Test merging hook configurations."""

    def test_merge_into_empty_base(self):
        base = {}
        new = {"Stop": [{"hooks": [{"type": "command", "command": "a"}]}]}
        result = merge_hooks(base, new)
        assert len(result["Stop"]) == 1

    def test_merge_combines_same_type(self):
        base = {"Stop": [{"hooks": [{"command": "a"}]}]}
        new = {"Stop": [{"hooks": [{"command": "b"}]}]}
        result = merge_hooks(base, new)
        assert len(result["Stop"]) == 2

    def test_merge_adds_new_type(self):
        base = {"Stop": [{"hooks": [{"command": "a"}]}]}
        new = {"PreToolUse": [{"hooks": [{"command": "b"}]}]}
        result = merge_hooks(base, new)
        assert "Stop" in result
        assert "PreToolUse" in result

    def test_merge_empty_new(self):
        base = {"Stop": [{"command": "a"}]}
        result = merge_hooks(base, {})
        assert result == {"Stop": [{"command": "a"}]}

    def test_merge_both_empty(self):
        result = merge_hooks({}, {})
        assert result == {}


# ===================================================================
# merge_manifests (lib.install_utils)
# ===================================================================


class TestMergeManifests:
    """Test merging profile + agent manifests."""

    def test_union_of_component_lists(self):
        profile = {"skills": ["spec"], "hooks": ["worktree"]}
        agent = {"skills": ["todo", "spec"], "hooks": ["notification"]}
        result = merge_manifests(profile, agent)
        assert result["skills"] == ["spec", "todo"]
        assert result["hooks"] == ["notification", "worktree"]

    def test_instructions_concatenated_profile_first(self):
        profile = {"instructions": ["workspace-routing"]}
        agent = {"instructions": ["kb-mode", "saving"]}
        result = merge_manifests(profile, agent)
        assert result["instructions"] == ["workspace-routing", "kb-mode", "saving"]

    def test_settings_deep_merged_agent_wins(self):
        profile = {
            "settings": {
                "knowledge_base": "/vault",
                "permissions": {"allow": ["Read(*)"]},
            }
        }
        agent = {
            "settings": {
                "defaultThinkingLevel": "medium",
                "permissions": {"allow": ["Write(*)"]},
            }
        }
        result = merge_manifests(profile, agent)
        assert result["settings"]["knowledge_base"] == "/vault"
        assert result["settings"]["defaultThinkingLevel"] == "medium"
        # Agent wins on conflict for nested dicts
        assert result["settings"]["permissions"]["allow"] == ["Write(*)"]

    def test_empty_manifests(self):
        result = merge_manifests({}, {})
        assert result["skills"] == []
        assert result["hooks"] == []
        assert result["instructions"] == []
        assert result["settings"] == {}

    def test_extensions_unioned(self):
        profile = {"extensions": ["ext-a"]}
        agent = {"extensions": ["ext-b", "ext-a"]}
        result = merge_manifests(profile, agent)
        assert result["extensions"] == ["ext-a", "ext-b"]

    def test_none_values_treated_as_empty(self):
        profile = {"skills": None, "hooks": ["worktree"]}
        agent = {"skills": ["spec"], "hooks": None}
        result = merge_manifests(profile, agent)
        assert result["skills"] == ["spec"]
        assert result["hooks"] == ["worktree"]


# ===================================================================
# resolve_runtime
# ===================================================================


class TestResolveRuntime:
    """Test runtime resolution from agent manifest."""

    def test_explicit_runtime(self):
        manifest = {"runtime": "claude-code", "target": ".claude"}
        assert install.resolve_runtime("my-agent", manifest) == "claude-code"

    def test_fallback_to_agent_name(self):
        manifest = {"target": ".claude"}
        assert install.resolve_runtime("claude-code", manifest) == "claude-code"

    def test_pi_runtime(self):
        manifest = {"runtime": "pi", "target": ".pi"}
        assert install.resolve_runtime("pi", manifest) == "pi"


# ===================================================================
# install (full integration)
# ===================================================================


class TestInstall:
    """Integration tests for the main install() function."""

    def _setup_basic(self, fake_repo, target, prompt_md="# Rules"):
        """Create a minimal profile + agent pair for testing."""
        make_profile(
            fake_repo["profiles"],
            "test-profile",
            manifest={"description": "test profile"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "description": "test agent",
                "runtime": "claude-code",
                "target": ".claude",
                "skills": [],
                "hooks": [],
                "pipelines": [],
                "external": [],
            },
            prompt_md=prompt_md,
        )

    def test_creates_claude_dir(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        self._setup_basic(fake_repo, target)
        install.install("test-profile", ["test-claude"], target)
        assert (target / ".claude").is_dir()
        assert (target / ".claude" / "settings.json").exists()
        assert (target / ".claude" / "CLAUDE.md").exists()

    def test_symlinks_skills(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_skill(fake_repo["skills"], "spec")
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "skills": ["spec"],
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        link = target / ".claude" / "skills" / "spec"
        assert link.is_symlink()
        assert link.resolve() == (fake_repo["skills"] / "spec").resolve()

    def test_symlinks_hooks(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_hook(fake_repo["hooks"], "notification")
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "hooks": ["notification"],
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        link = target / ".claude" / "hooks" / "notification"
        assert link.is_symlink()
        assert link.resolve() == (fake_repo["hooks"] / "notification").resolve()

    def test_symlinks_pipelines(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_pipeline(fake_repo["pipelines"], "workspace")
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "pipelines": ["workspace"],
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        link = target / "pipelines" / "workspace"
        assert link.is_symlink()
        assert link.resolve() == (fake_repo["pipelines"] / "workspace").resolve()

    def test_does_not_overwrite_existing_symlinks(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_skill(fake_repo["skills"], "spec")
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "skills": ["spec"],
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        link = target / ".claude" / "skills" / "spec"
        assert link.is_symlink()

        # Second install should not raise
        install.install("p1", ["test-claude"], target)
        assert link.is_symlink()

    def test_skips_missing_skill_source(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "skills": ["nonexistent-skill"],
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        assert not (target / ".claude" / "skills" / "nonexistent-skill").exists()

    def test_skips_missing_hook_source(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "hooks": ["ghost-hook"],
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        assert not (target / ".claude" / "hooks" / "ghost-hook").exists()

    def test_skips_missing_pipeline_source(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "pipelines": ["ghost-pipe"],
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        assert not (target / "pipelines" / "ghost-pipe").exists()

    def test_writes_claude_md(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
            },
            prompt_md="## My Rules",
        )
        install.install("p1", ["test-claude"], target)
        content = (target / ".claude" / "CLAUDE.md").read_text()
        assert "## My Rules" in content

    def test_writes_settings_json(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        assert "hooks" in settings

    def test_hook_config_merged_into_settings(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        hooks_json = {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "{hook_dir}/hook.sh stop",
                            "timeout": 5,
                        }
                    ]
                }
            ]
        }
        make_hook(fake_repo["hooks"], "my-hook", hooks_json=hooks_json)
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "hooks": ["my-hook"],
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        stop_hooks = settings["hooks"]["Stop"]
        assert len(stop_hooks) == 1
        expected_cmd = str(target / ".claude" / "hooks" / "my-hook") + "/hook.sh stop"
        assert stop_hooks[0]["hooks"][0]["command"] == expected_cmd

    def test_pipelines_dir_not_created_when_empty(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        self._setup_basic(fake_repo, target)
        install.install("test-profile", ["test-claude"], target)
        assert not (target / "pipelines").exists()

    def test_permissions_from_merged_settings(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={
                "description": "p1",
                "settings": {"permissions": {"allow": ["Read(*)"]}},
            },
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "settings": {"permissions": {"allow": ["Write(*)"]}},
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        # Agent settings win on conflict during merge
        assert "permissions" in settings


# ===================================================================
# list_available
# ===================================================================


class TestListAvailable:
    """Test listing available profiles and agents."""

    def test_lists_profiles_and_agents(self, fake_repo):
        make_profile(
            fake_repo["profiles"],
            "alpha",
            manifest={"description": "Alpha profile"},
        )
        make_agent(
            fake_repo["agents"],
            "beta-agent",
            manifest={
                "description": "Beta agent",
                "runtime": "claude-code",
                "target": ".claude",
            },
        )
        # Just verify it doesn't crash
        install.list_available()

    def test_empty_dirs(self, fake_repo):
        install.list_available()


# ===================================================================
# main (CLI argument parsing)
# ===================================================================


class TestMain:
    """Test CLI argument parsing in main()."""

    def test_list_flag(self, fake_repo):
        with patch("sys.argv", ["install.py", "--list"]):
            with patch.object(install, "list_available") as mock_list:
                install.main()
                mock_list.assert_called_once()

    def test_profile_and_agents_flags(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_profile(
            fake_repo["profiles"],
            "base",
            manifest={"description": "base"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
            },
            prompt_md="# Rules",
        )
        with patch(
            "sys.argv",
            [
                "install.py",
                "--profile",
                "base",
                "--agents",
                "test-claude",
                "--target",
                str(target),
            ],
        ):
            install.main()
        assert (target / ".claude").is_dir()

    def test_interactive_mode(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_profile(
            fake_repo["profiles"],
            "base",
            manifest={"description": "Base"},
        )
        make_agent(
            fake_repo["agents"],
            "claude-code/test",
            manifest={
                "description": "Test",
                "runtime": "claude-code",
                "target": ".claude",
            },
            prompt_md="# Rules",
        )
        with (
            patch("sys.argv", ["install.py", "--target", str(target)]),
            patch.object(install, "Prompt") as mock_prompt,
        ):
            # First ask: profile selection, second ask: agent selection
            mock_prompt.ask.side_effect = ["1", "1"]
            install.main()
        assert (target / ".claude").is_dir()

    def test_choose_profile_interactively_returns_selected(self, fake_repo):
        make_profile(
            fake_repo["profiles"],
            "base",
            manifest={"description": "Base"},
        )
        with patch.object(install, "Prompt") as mock_prompt:
            mock_prompt.ask.return_value = "1"
            assert install.choose_profile_interactively() == "base"

    def test_choose_agents_interactively_returns_selected(self, fake_repo):
        make_agent(
            fake_repo["agents"],
            "claude-code/test",
            manifest={
                "description": "Test",
                "runtime": "claude-code",
                "target": ".claude",
            },
        )
        with patch.object(install, "Prompt") as mock_prompt:
            mock_prompt.ask.return_value = "1"
            result = install.choose_agents_interactively()
            assert result == ["claude-code/test"]

    def test_interactive_no_selection(self, fake_repo, tmp_path):
        make_profile(
            fake_repo["profiles"],
            "base",
            manifest={"description": "Base"},
        )
        with (
            patch("sys.argv", ["install.py"]),
            patch.object(install, "Prompt") as mock_prompt,
        ):
            mock_prompt.ask.return_value = "99"
            install.main()

    def test_interactive_non_numeric_selection(self, fake_repo):
        make_profile(
            fake_repo["profiles"],
            "base",
            manifest={"description": "Base"},
        )
        with patch.object(install, "Prompt") as mock_prompt:
            mock_prompt.ask.return_value = "abc"
            assert install.choose_profile_interactively() is None

    def test_profile_without_agents_prints_error(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        with patch(
            "sys.argv",
            ["install.py", "--profile", "base", "--target", str(target)],
        ):
            # Should print error about --agents required
            install.main()


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    """Edge cases and unusual scenarios."""

    def test_hook_dir_placeholder_in_nested_json(self, fake_repo):
        """Placeholder appears in deeply nested values."""
        hooks_json = {
            "PreToolUse": [
                {
                    "matcher": "Read",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "{hook_dir}/run.sh",
                            "env": {"HOOK_PATH": "{hook_dir}"},
                        }
                    ],
                }
            ]
        }
        make_hook(fake_repo["hooks"], "deep", hooks_json=hooks_json)
        result = install.load_hook_config("deep", Path("/abs/hooks/deep"))
        assert (
            result["PreToolUse"][0]["hooks"][0]["command"] == "/abs/hooks/deep/run.sh"
        )
        assert (
            result["PreToolUse"][0]["hooks"][0]["env"]["HOOK_PATH"] == "/abs/hooks/deep"
        )

    def test_install_idempotent(self, fake_repo, tmp_path):
        """Running install twice produces same result."""
        target = tmp_path / "project"
        target.mkdir()
        make_skill(fake_repo["skills"], "spec")
        make_hook(fake_repo["hooks"], "notification")
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "skills": ["spec"],
                "hooks": ["notification"],
            },
            prompt_md="Content",
        )
        install.install("p1", ["test-claude"], target)
        first_claude_md = (target / ".claude" / "CLAUDE.md").read_text()

        install.install("p1", ["test-claude"], target)
        second_claude_md = (target / ".claude" / "CLAUDE.md").read_text()

        assert first_claude_md == second_claude_md
        assert (target / ".claude" / "skills" / "spec").is_symlink()
        assert (target / ".claude" / "hooks" / "notification").is_symlink()

    def test_hooks_reset_on_reinstall(self, fake_repo, tmp_path):
        """Hooks are reset on each install to avoid stale entries."""
        target = tmp_path / "project"
        target.mkdir()
        hooks_json = {
            "Stop": [{"hooks": [{"type": "command", "command": "{hook_dir}/hook.sh"}]}]
        }
        make_hook(fake_repo["hooks"], "my-hook", hooks_json=hooks_json)
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "hooks": ["my-hook"],
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        settings1 = json.loads((target / ".claude" / "settings.json").read_text())
        assert len(settings1["hooks"]["Stop"]) == 1

        install.install("p1", ["test-claude"], target)
        settings2 = json.loads((target / ".claude" / "settings.json").read_text())
        assert len(settings2["hooks"]["Stop"]) == 1

    def test_target_doesnt_exist_yet(self, fake_repo, tmp_path):
        """Install creates project dir even if target has no .claude yet."""
        target = tmp_path / "fresh-project"
        target.mkdir()
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
            },
            prompt_md="# Rules",
        )
        install.install("p1", ["test-claude"], target)
        assert (target / ".claude").is_dir()
        assert (target / ".claude" / "settings.json").exists()


# ===================================================================
# Frontmatter parsing
# ===================================================================


class TestFrontmatter:
    """Test YAML frontmatter parsing and stripping."""

    def test_parse_with_frontmatter(self):
        metadata, body = install.parse_frontmatter(
            '---\n{"required_skills": ["orchestrator"]}\n---\n\n## Title\nBody'
        )
        assert metadata["required_skills"] == ["orchestrator"]
        assert "## Title" in body
        assert "---" not in body

    def test_parse_without_frontmatter(self):
        content = "## Title\nBody text"
        metadata, body = install.parse_frontmatter(content)
        assert metadata == {}
        assert body == content

    def test_strip_frontmatter(self):
        content = '---\n{"key": "value"}\n---\n\nBody'
        result = install.strip_frontmatter(content)
        assert "---" not in result
        assert "Body" in result

    def test_strip_no_frontmatter(self):
        content = "Just plain text"
        assert install.strip_frontmatter(content) == content


# ===================================================================
# Dependency validation
# ===================================================================


class TestValidateCommonDependencies:
    """Test common file skill dependency validation."""

    def test_missing_skill_returns_error(self, fake_repo):
        make_common(
            fake_repo["common"],
            "orchestration",
            "## Orchestration",
            requires={"skills": ["orchestrator"]},
        )
        errors = install.validate_common_dependencies(
            ["orchestration"], {"todo", "review"}
        )
        assert len(errors) == 1
        assert "orchestrator" in errors[0]

    def test_satisfied_deps_returns_empty(self, fake_repo):
        make_common(
            fake_repo["common"],
            "orchestration",
            "## Orchestration",
            requires={"skills": ["orchestrator"]},
        )
        errors = install.validate_common_dependencies(
            ["orchestration"], {"orchestrator"}
        )
        assert errors == []

    def test_no_frontmatter_no_errors(self, fake_repo):
        make_common(fake_repo["common"], "skills", "## Skills")
        errors = install.validate_common_dependencies(["skills"], set())
        assert errors == []

    def test_missing_file_returns_error(self, fake_repo):
        errors = install.validate_common_dependencies(["nonexistent"], set())
        assert len(errors) == 1
        assert "not found" in errors[0]

    def test_multiple_missing_skills(self, fake_repo):
        make_common(
            fake_repo["common"],
            "multi",
            "## Multi",
            requires={"skills": ["a", "b", "c"]},
        )
        errors = install.validate_common_dependencies(["multi"], {"b"})
        assert len(errors) == 1
        assert "a" in errors[0]
        assert "c" in errors[0]


# ===================================================================
# Template include extraction
# ===================================================================


class TestExtractCommonNames:
    """Test extracting common file names from template include directives."""

    def test_extracts_common_includes(self):
        content = "# Title\n{{include:common/skills.md}}\n{{include:common/git.md}}"
        names = install.extract_common_names_from_template(content)
        assert names == ["skills", "git"]

    def test_ignores_non_common_includes(self):
        content = "{{include:profiles/kb/instructions/saving.md}}\n{{include:common/skills.md}}"
        names = install.extract_common_names_from_template(content)
        assert names == ["skills"]

    def test_empty_content(self):
        assert install.extract_common_names_from_template("") == []


# ===================================================================
# Manifest common and instructions
# ===================================================================


class TestManifestCommonAndInstructions:
    """Integration tests for common and instructions with profile + agent."""

    def test_common_sections_appended(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_common(fake_repo["common"], "skills", "## Skills\nUse skills.")
        make_common(fake_repo["common"], "git", "## Git\nCommit rules.")
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "claude-code/test",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "system_prompt": {"common": ["skills", "git"]},
            },
            prompt_md="# My Agent",
        )
        install.install("p1", ["claude-code/test"], target)
        content = (target / ".claude" / "CLAUDE.md").read_text()
        assert content.startswith("# My Agent")
        assert "## Skills" in content
        assert "## Git" in content

    def test_instructions_appended_before_common(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_common(fake_repo["common"], "git", "## Git\nCommit rules.")
        make_instruction(
            fake_repo["profiles"], "p1", "saving", "## Saving\nSave notes."
        )
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={
                "description": "p1",
                "instructions": ["saving"],
            },
        )
        make_agent(
            fake_repo["agents"],
            "claude-code/test",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "system_prompt": {"common": ["git"]},
            },
            prompt_md="# KB Mode",
        )
        install.install("p1", ["claude-code/test"], target)
        content = (target / ".claude" / "CLAUDE.md").read_text()
        saving_pos = content.index("## Saving")
        git_pos = content.index("## Git")
        assert saving_pos < git_pos

    def test_frontmatter_stripped_from_common(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_common(
            fake_repo["common"],
            "orchestration",
            "## Orchestration\nDelegate work.",
            requires={"skills": ["orchestrator"]},
        )
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "claude-code/test",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "skills": ["orchestrator"],
                "system_prompt": {"common": ["orchestration"]},
            },
            prompt_md="# Dev",
        )
        install.install("p1", ["claude-code/test"], target)
        content = (target / ".claude" / "CLAUDE.md").read_text()
        assert "---" not in content
        assert "requires" not in content
        assert "## Orchestration" in content

    def test_missing_skill_dep_fails_install(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_common(
            fake_repo["common"],
            "orchestration",
            "## Orchestration",
            requires={"skills": ["orchestrator"]},
        )
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "claude-code/test",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "skills": ["todo"],
                "system_prompt": {"common": ["orchestration"]},
            },
            prompt_md="# Dev",
        )
        with pytest.raises(ValueError, match="Common file dependencies not satisfied"):
            install.install("p1", ["claude-code/test"], target)

    def test_missing_instruction_file_raises(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={
                "description": "p1",
                "instructions": ["nonexistent"],
            },
        )
        make_agent(
            fake_repo["agents"],
            "claude-code/test",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
            },
            prompt_md="# Dev",
        )
        with pytest.raises(FileNotFoundError):
            install.install("p1", ["claude-code/test"], target)

    def test_missing_common_file_fails_install(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "claude-code/test",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "system_prompt": {"common": ["nonexistent"]},
            },
            prompt_md="# Dev",
        )
        with pytest.raises((ValueError, FileNotFoundError)):
            install.install("p1", ["claude-code/test"], target)


# ===================================================================
# Installation registry
# ===================================================================


class TestRegistry:
    """Test installation registry (installations.yaml) tracking."""

    def test_load_empty_registry(self, fake_repo):
        result = install.load_registry()
        assert result == []

    def test_update_registry_creates_file(self, fake_repo):
        install.update_registry("personal", Path("/some/target"))
        registry_path = fake_repo["root"] / "installations.yaml"
        assert registry_path.exists()
        entries = install.load_registry()
        assert len(entries) == 1
        assert entries[0]["profile"] == "personal"
        assert entries[0]["target"] == "/some/target"

    def test_update_registry_stores_agents_and_project_dirs(self, fake_repo):
        install.update_registry(
            "personal",
            Path("/some/target"),
            agents=["claude-code", "pi"],
            project_dirs={
                "claude-code": Path("/some/target/.claude"),
                "pi": Path("/some/target/.pi"),
            },
        )
        entries = install.load_registry()
        assert entries[0]["agents"] == ["claude-code", "pi"]
        assert entries[0]["project_dirs"]["claude-code"] == "/some/target/.claude"

    def test_update_registry_upserts_by_target(self, fake_repo):
        install.update_registry("personal", Path("/some/target"))
        install.update_registry("work", Path("/some/target"))
        entries = install.load_registry()
        assert len(entries) == 1
        assert entries[0]["profile"] == "work"

    def test_update_registry_multiple_targets(self, fake_repo):
        install.update_registry("personal", Path("/target/a"))
        install.update_registry("work", Path("/target/b"))
        entries = install.load_registry()
        assert len(entries) == 2

    def test_update_registry_with_knowledge_base(self, fake_repo):
        install.update_registry("kb", Path("/target"), Path("/my/vault"))
        entries = install.load_registry()
        assert entries[0]["knowledge_base"] == "/my/vault"

    def test_install_updates_registry(self, fake_repo):
        """A successful install() call should auto-update the registry."""
        make_profile(
            fake_repo["profiles"],
            "test-profile",
            manifest={"description": "test"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
            },
            prompt_md="# Test",
        )
        target = fake_repo["root"] / "my_project"
        target.mkdir()
        install.install("test-profile", ["test-claude"], target)
        entries = install.load_registry()
        assert len(entries) == 1
        assert entries[0]["profile"] == "test-profile"
        assert entries[0]["target"] == str(target.resolve())
        assert entries[0]["agents"] == ["test-claude"]

    def test_install_all_reinstalls(self, fake_repo):
        make_skill(fake_repo["skills"], "spec")
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
                "skills": ["spec"],
            },
            prompt_md="# P1",
        )
        target = fake_repo["root"] / "t1"
        target.mkdir()
        install.update_registry(
            "p1",
            target,
            agents=["test-claude"],
            project_dirs={"test-claude": target / ".claude"},
        )
        count = install.install_all()
        assert count == 1
        assert (target / ".claude" / "CLAUDE.md").exists()

    def test_install_all_empty_registry(self, fake_repo):
        count = install.install_all()
        assert count == 0

    def test_install_all_runs_all_entries(self, fake_repo):
        make_profile(
            fake_repo["profiles"],
            "p1",
            manifest={"description": "p1"},
        )
        make_profile(
            fake_repo["profiles"],
            "p2",
            manifest={"description": "p2"},
        )
        make_agent(
            fake_repo["agents"],
            "test-claude",
            manifest={
                "runtime": "claude-code",
                "target": ".claude",
            },
            prompt_md="# Rules",
        )
        t1 = fake_repo["root"] / "t1"
        t2 = fake_repo["root"] / "t2"
        t1.mkdir()
        t2.mkdir()
        install.update_registry(
            "p1",
            t1,
            agents=["test-claude"],
            project_dirs={"test-claude": t1 / ".claude"},
        )
        install.update_registry(
            "p2",
            t2,
            agents=["test-claude"],
            project_dirs={"test-claude": t2 / ".claude"},
        )
        count = install.install_all()
        assert count == 2
        assert (t1 / ".claude" / "CLAUDE.md").exists()
        assert (t2 / ".claude" / "CLAUDE.md").exists()


# ===================================================================
# migrate_registry_entry
# ===================================================================


class TestMigrateRegistryEntry:
    """Test v1 → v2 registry migration."""

    def test_already_v2_unchanged(self):
        entry = {"profile": "personal", "target": "/t"}
        result = install.migrate_registry_entry(entry)
        assert result == entry

    def test_v1_dev_workspace_maps_to_personal(self):
        entry = {"preset": "dev-workspace", "target": "/t"}
        result = install.migrate_registry_entry(entry)
        assert result["profile"] == "personal"
        assert "preset" not in result
        assert result["target"] == "/t"

    def test_v1_knowledge_base_maps_to_knowledge_base(self):
        entry = {"preset": "knowledge-base", "target": "/t"}
        result = install.migrate_registry_entry(entry)
        assert result["profile"] == "knowledge-base"

    def test_v1_work_maps_to_work(self):
        entry = {"preset": "work", "target": "/t"}
        result = install.migrate_registry_entry(entry)
        assert result["profile"] == "work"

    def test_v1_unknown_preset_uses_name_as_is(self):
        entry = {"preset": "custom", "target": "/t"}
        result = install.migrate_registry_entry(entry)
        assert result["profile"] == "custom"

    def test_preserves_other_fields(self):
        entry = {
            "preset": "dev-workspace",
            "target": "/t",
            "knowledge_base": "/vault",
            "agents": ["claude-code"],
        }
        result = install.migrate_registry_entry(entry)
        assert result["knowledge_base"] == "/vault"
        assert result["agents"] == ["claude-code/default"]


# ===================================================================
# Shipped manifests validation
# ===================================================================


class TestShippedManifests:
    """Test that shipped profiles and agents have valid manifests."""

    def test_shipped_profiles_have_manifests(self):
        for profile in ["personal", "work", "knowledge-base"]:
            manifest_path = REPO_ROOT / "profiles" / profile / "manifest.yaml"
            assert manifest_path.exists(), f"Profile {profile} missing manifest.yaml"

    def test_shipped_agents_have_manifests(self):
        for agent in ["claude-code/default", "pi/nefor"]:
            manifest_path = REPO_ROOT / "agents" / agent / "manifest.yaml"
            assert manifest_path.exists(), f"Agent {agent} missing manifest.yaml"

    def test_shipped_agents_have_runtime_and_target(self):
        import yaml as real_yaml

        for agent in ["claude-code/default", "pi/nefor"]:
            manifest_path = REPO_ROOT / "agents" / agent / "manifest.yaml"
            manifest = real_yaml.safe_load(manifest_path.read_text())
            assert "runtime" in manifest, f"Agent {agent} missing 'runtime'"
            assert "target" in manifest, f"Agent {agent} missing 'target'"
