"""Tests for install.py — the core installer."""

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
    - JSON content (produced by make_preset via json.dumps)
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


# ---------------------------------------------------------------------------
# Helpers to build fake repo layouts inside tmp_path
# ---------------------------------------------------------------------------


def make_preset(
    presets_dir: Path,
    name: str,
    manifest: dict | None = None,
    settings: dict | None = None,
    claude_md: str | None = None,
):
    """Create a preset directory with optional manifest, settings, and claude.md."""
    d = presets_dir / name
    d.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (d / "manifest.yaml").write_text(json.dumps(manifest))
    if settings is not None:
        (d / "settings.json").write_text(json.dumps(settings))
    if claude_md is not None:
        (d / "claude.md").write_text(claude_md)


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


def make_common(common_dir: Path, name: str, content: str, requires: dict | None = None):
    """Create a common file with optional frontmatter.

    Uses JSON in the frontmatter block so the mock yaml parser can handle it.
    """
    if requires:
        frontmatter_data = json.dumps({"required_skills": requires.get("skills", [])})
        content = f"---\n{frontmatter_data}\n---\n\n{content}"
    (common_dir / f"{name}.md").write_text(content)


def make_instruction(presets_dir: Path, preset: str, name: str, content: str):
    """Create a preset instruction file."""
    d = presets_dir / preset / "instructions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(content)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_repo(tmp_path):
    """Build a fake repo layout and patch install module globals to use it."""
    presets_dir = tmp_path / "presets"
    skills_dir = tmp_path / "skills"
    hooks_dir = tmp_path / "hooks"
    pipelines_dir = tmp_path / "pipelines"
    common_dir = tmp_path / "common"
    presets_dir.mkdir()
    skills_dir.mkdir()
    hooks_dir.mkdir()
    pipelines_dir.mkdir()
    common_dir.mkdir()

    with (
        patch.object(install, "REPO_ROOT", tmp_path),
        patch.object(install, "PRESETS_DIR", presets_dir),
        patch.object(install, "SKILLS_DIR", skills_dir),
        patch.object(install, "HOOKS_DIR", hooks_dir),
        patch.object(install, "PIPELINES_DIR", pipelines_dir),
        patch.object(install, "COMMON_DIR", common_dir),
    ):
        yield {
            "root": tmp_path,
            "presets": presets_dir,
            "skills": skills_dir,
            "hooks": hooks_dir,
            "pipelines": pipelines_dir,
            "common": common_dir,
        }


# ===================================================================
# load_manifest
# ===================================================================


class TestLoadManifest:
    """Test loading manifest.yaml for a preset."""

    def test_loads_valid_manifest(self, fake_repo):
        manifest = {
            "description": "Test preset",
            "skills": ["spec"],
            "hooks": ["link-proxy"],
            "pipelines": [],
            "external": [],
        }
        make_preset(fake_repo["presets"], "test", manifest=manifest)
        result = install.load_manifest("test")
        assert result["description"] == "Test preset"
        assert result["skills"] == ["spec"]
        assert result["hooks"] == ["link-proxy"]

    def test_missing_preset_returns_empty(self, fake_repo):
        result = install.load_manifest("nonexistent")
        assert result == {}

    def test_empty_manifest(self, fake_repo):
        d = fake_repo["presets"] / "empty"
        d.mkdir()
        (d / "manifest.yaml").write_text("")
        result = install.load_manifest("empty")
        # yaml.safe_load returns None for empty string
        assert result is None

    def test_manifest_with_only_description(self, fake_repo):
        make_preset(
            fake_repo["presets"],
            "minimal",
            manifest={"description": "Minimal"},
        )
        result = install.load_manifest("minimal")
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
# merge_hooks
# ===================================================================


class TestMergeHooks:
    """Test merging hook configurations."""

    def test_merge_into_empty_base(self):
        base = {}
        new = {"Stop": [{"hooks": [{"type": "command", "command": "a"}]}]}
        result = install.merge_hooks(base, new)
        assert len(result["Stop"]) == 1

    def test_merge_combines_same_type(self):
        base = {"Stop": [{"hooks": [{"command": "a"}]}]}
        new = {"Stop": [{"hooks": [{"command": "b"}]}]}
        result = install.merge_hooks(base, new)
        assert len(result["Stop"]) == 2

    def test_merge_adds_new_type(self):
        base = {"Stop": [{"hooks": [{"command": "a"}]}]}
        new = {"PreToolUse": [{"hooks": [{"command": "b"}]}]}
        result = install.merge_hooks(base, new)
        assert "Stop" in result
        assert "PreToolUse" in result

    def test_merge_empty_new(self):
        base = {"Stop": [{"command": "a"}]}
        result = install.merge_hooks(base, {})
        assert result == {"Stop": [{"command": "a"}]}

    def test_merge_both_empty(self):
        result = install.merge_hooks({}, {})
        assert result == {}


# ===================================================================
# load_existing_settings
# ===================================================================


class TestLoadExistingSettings:
    """Test loading existing .claude/settings.json."""

    def test_loads_existing(self, tmp_path):
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        settings = {"hooks": {"Stop": [{"command": "x"}]}, "custom": True}
        (claude_dir / "settings.json").write_text(json.dumps(settings))
        result = install.load_existing_settings(tmp_path)
        assert result["custom"] is True
        assert "Stop" in result["hooks"]

    def test_missing_returns_default(self, tmp_path):
        result = install.load_existing_settings(tmp_path)
        assert result == {"hooks": {}, "permissions": {}}


# ===================================================================
# merge_settings
# ===================================================================


class TestMergeSettings:
    """Test merging settings.json from presets."""

    def test_merges_single_preset(self, fake_repo, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={"description": "p1"},
            settings={"hooks": {"Stop": [{"command": "a"}]}},
        )
        result = install.merge_settings("p1", target)
        assert "Stop" in result["hooks"]
        assert len(result["hooks"]["Stop"]) == 1

    def test_preset_without_settings(self, fake_repo, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "no-settings",
            manifest={"description": "none"},
        )
        result = install.merge_settings("no-settings", target)
        assert result == {"hooks": {}, "permissions": {}}

    def test_preserves_existing_settings(self, fake_repo, tmp_path):
        target = tmp_path / "target"
        claude_dir = target / ".claude"
        claude_dir.mkdir(parents=True)
        existing = {"hooks": {"Stop": [{"command": "existing"}]}, "other_key": "keep"}
        (claude_dir / "settings.json").write_text(json.dumps(existing))

        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={"description": "p1"},
            settings={"hooks": {"Stop": [{"command": "new"}]}},
        )
        result = install.merge_settings("p1", target)
        assert result["other_key"] == "keep"
        # Hooks are reset on each install to avoid stale entries
        assert len(result["hooks"]["Stop"]) == 1
        assert result["hooks"]["Stop"][0]["command"] == "new"


# ===================================================================
# collect_components
# ===================================================================


class TestCollectComponents:
    """Test collecting skills, hooks, pipelines, external from manifests."""

    def test_collects_from_single_preset(self, fake_repo):
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "description": "test",
                "skills": ["spec"],
                "hooks": ["link-proxy"],
                "pipelines": ["workspace"],
                "external": ["org/repo#skill"],
            },
        )
        result = install.collect_components("p1")
        assert result["skills"] == {"spec"}
        assert result["hooks"] == {"link-proxy"}
        assert result["pipelines"] == {"workspace"}
        assert result["external"] == {"org/repo#skill"}

    def test_missing_keys_in_manifest(self, fake_repo):
        make_preset(
            fake_repo["presets"],
            "minimal",
            manifest={"description": "just a description"},
        )
        result = install.collect_components("minimal")
        assert result["skills"] == set()
        assert result["hooks"] == set()
        assert result["pipelines"] == set()
        assert result["external"] == set()

    def test_missing_preset(self, fake_repo):
        result = install.collect_components("nonexistent")
        # load_manifest returns {} for missing, .get returns []
        assert result["skills"] == set()


# ===================================================================
# resolve_dependencies
# ===================================================================


class TestResolveDependencies:
    """Test dependency resolution logic."""

    def test_workspace_adds_link_proxy(self):
        components = {
            "skills": set(),
            "hooks": set(),
            "pipelines": {"workspace"},
            "external": set(),
        }
        result = install.resolve_dependencies(components)
        assert "link-proxy" in result["hooks"]

    def test_no_workspace_no_change(self):
        components = {
            "skills": {"spec"},
            "hooks": {"notification"},
            "pipelines": set(),
            "external": set(),
        }
        result = install.resolve_dependencies(components)
        assert result["hooks"] == {"notification"}

    def test_link_proxy_not_duplicated(self):
        components = {
            "skills": set(),
            "hooks": {"link-proxy"},
            "pipelines": {"workspace"},
            "external": set(),
        }
        result = install.resolve_dependencies(components)
        # Still just one link-proxy (set dedup)
        assert result["hooks"] == {"link-proxy"}


# ===================================================================
# install (full integration)
# ===================================================================


class TestInstall:
    """Integration tests for the main install() function."""

    def test_creates_claude_dir(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "base",
            manifest={
                "description": "base",
                "skills": [],
                "hooks": [],
                "pipelines": [],
                "external": [],
            },
            settings={"hooks": {}},
            claude_md="Base rules",
        )
        install.install("base", target)
        assert (target / ".claude").is_dir()
        assert (target / ".claude" / "settings.json").exists()
        assert (target / ".claude" / "CLAUDE.md").exists()

    def test_symlinks_skills(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_skill(fake_repo["skills"], "spec")
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={"skills": ["spec"], "hooks": [], "pipelines": [], "external": []},
            settings={"hooks": {}},
        )
        install.install("p1", target)
        link = target / ".claude" / "skills" / "spec"
        assert link.is_symlink()
        assert link.resolve() == (fake_repo["skills"] / "spec").resolve()

    def test_symlinks_hooks(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_hook(fake_repo["hooks"], "notification")
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": [],
                "hooks": ["notification"],
                "pipelines": [],
                "external": [],
            },
            settings={"hooks": {}},
        )
        install.install("p1", target)
        link = target / ".claude" / "hooks" / "notification"
        assert link.is_symlink()
        assert link.resolve() == (fake_repo["hooks"] / "notification").resolve()

    def test_symlinks_pipelines(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_pipeline(fake_repo["pipelines"], "workspace")
        # workspace triggers link-proxy dependency, so create that too
        make_hook(fake_repo["hooks"], "link-proxy")
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": [],
                "hooks": [],
                "pipelines": ["workspace"],
                "external": [],
            },
            settings={"hooks": {}},
        )
        install.install("p1", target)
        link = target / "pipelines" / "workspace"
        assert link.is_symlink()
        assert link.resolve() == (fake_repo["pipelines"] / "workspace").resolve()

    def test_does_not_overwrite_existing_symlinks(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_skill(fake_repo["skills"], "spec")
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={"skills": ["spec"], "hooks": [], "pipelines": [], "external": []},
            settings={"hooks": {}},
        )
        # First install
        install.install("p1", target)
        link = target / ".claude" / "skills" / "spec"
        assert link.is_symlink()

        # Second install should not raise
        install.install("p1", target)
        assert link.is_symlink()

    def test_skips_missing_skill_source(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        # Skill not created in skills_dir
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": ["nonexistent-skill"],
                "hooks": [],
                "pipelines": [],
                "external": [],
            },
            settings={"hooks": {}},
        )
        install.install("p1", target)
        assert not (target / ".claude" / "skills" / "nonexistent-skill").exists()

    def test_skips_missing_hook_source(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": [],
                "hooks": ["ghost-hook"],
                "pipelines": [],
                "external": [],
            },
            settings={"hooks": {}},
        )
        install.install("p1", target)
        assert not (target / ".claude" / "hooks" / "ghost-hook").exists()

    def test_skips_missing_pipeline_source(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": [],
                "hooks": [],
                "pipelines": ["ghost-pipe"],
                "external": [],
            },
            settings={"hooks": {}},
        )
        install.install("p1", target)
        assert not (target / "pipelines" / "ghost-pipe").exists()

    def test_writes_claude_md(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={"skills": [], "hooks": [], "pipelines": [], "external": []},
            settings={"hooks": {}},
            claude_md="## My Rules",
        )
        install.install("p1", target)
        content = (target / ".claude" / "CLAUDE.md").read_text()
        assert "## My Rules" in content

    def test_writes_settings_json(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={"skills": [], "hooks": [], "pipelines": [], "external": []},
            settings={"hooks": {"Stop": [{"command": "do-stop"}]}},
        )
        install.install("p1", target)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        assert "Stop" in settings["hooks"]

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
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": [],
                "hooks": ["my-hook"],
                "pipelines": [],
                "external": [],
            },
            settings={"hooks": {}},
        )
        install.install("p1", target)
        settings = json.loads((target / ".claude" / "settings.json").read_text())
        # Hook config should be merged with {hook_dir} resolved
        stop_hooks = settings["hooks"]["Stop"]
        assert len(stop_hooks) == 1
        expected_cmd = str(target / ".claude" / "hooks" / "my-hook") + "/hook.sh stop"
        assert stop_hooks[0]["hooks"][0]["command"] == expected_cmd

    def test_pipelines_dir_not_created_when_empty(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={"skills": [], "hooks": [], "pipelines": [], "external": []},
            settings={"hooks": {}},
        )
        install.install("p1", target)
        assert not (target / "pipelines").exists()

    def test_workspace_pipeline_auto_adds_link_proxy(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_pipeline(fake_repo["pipelines"], "workspace")
        make_hook(fake_repo["hooks"], "link-proxy")
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": [],
                "hooks": [],
                "pipelines": ["workspace"],
                "external": [],
            },
            settings={"hooks": {}},
        )
        install.install("p1", target)
        # link-proxy should be auto-added by resolve_dependencies
        assert (target / ".claude" / "hooks" / "link-proxy").is_symlink()


# ===================================================================
# list_presets
# ===================================================================


class TestListPresets:
    """Test listing available presets."""

    def test_lists_presets(self, fake_repo, capsys):
        make_preset(
            fake_repo["presets"],
            "alpha",
            manifest={"description": "Alpha preset"},
        )
        make_preset(
            fake_repo["presets"],
            "beta",
            manifest={"description": "Beta preset"},
        )
        install.list_presets()
        # Rich output goes to its own console, not captured by capsys.
        # We just verify it doesn't crash.

    def test_empty_presets_dir(self, fake_repo):
        # No presets created, should not crash
        install.list_presets()


# ===================================================================
# main (CLI argument parsing)
# ===================================================================


class TestMain:
    """Test CLI argument parsing in main()."""

    def test_list_flag(self, fake_repo):
        with patch("sys.argv", ["install.py", "--list"]):
            with patch.object(install, "list_presets") as mock_list:
                install.main()
                mock_list.assert_called_once()

    def test_presets_flag(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "base",
            manifest={"skills": [], "hooks": [], "pipelines": [], "external": []},
            settings={"hooks": {}},
        )
        with patch(
            "sys.argv", ["install.py", "--preset", "base", "--target", str(target)]
        ):
            install.main()
        assert (target / ".claude").is_dir()

    def test_interactive_mode(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "base",
            manifest={
                "description": "Base",
                "skills": [],
                "hooks": [],
                "pipelines": [],
                "external": [],
            },
            settings={"hooks": {}},
        )
        with (
            patch("sys.argv", ["install.py", "--target", str(target)]),
            patch.object(install, "Prompt") as mock_prompt,
        ):
            mock_prompt.ask.return_value = "1"
            install.main()
        assert (target / ".claude").is_dir()

    def test_interactive_no_selection(self, fake_repo, tmp_path):
        make_preset(
            fake_repo["presets"],
            "base",
            manifest={"description": "Base"},
        )
        with (
            patch("sys.argv", ["install.py"]),
            patch.object(install, "Prompt") as mock_prompt,
        ):
            # Select index out of range
            mock_prompt.ask.return_value = "99"
            install.main()
            # Should print "No presets selected" and return, not crash


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    """Edge cases and unusual scenarios."""

    def test_preset_with_none_manifest_values(self, fake_repo, tmp_path):
        """Manifest with explicit None values for component lists."""
        target = tmp_path / "project"
        target.mkdir()
        # Write manifest with null values
        d = fake_repo["presets"] / "nulls"
        d.mkdir()
        (d / "manifest.yaml").write_text(
            "description: Nulls\nskills:\nhooks:\npipelines:\nexternal:\n"
        )
        make_preset(
            fake_repo["presets"],
            "nulls",
            settings={"hooks": {}},
        )
        # collect_components calls .get(key, []) which returns None for yaml null
        # The set.update(None) would fail; verify behavior
        # Actually yaml null -> None, manifest.get("skills") -> None, not []
        # But .get("skills", []) should return None since key exists with None
        # This tests that the code handles None gracefully or not
        with pytest.raises(TypeError):
            install.collect_components("nulls")

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
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": ["spec"],
                "hooks": ["notification"],
                "pipelines": [],
                "external": [],
            },
            settings={"hooks": {}},
            claude_md="Content",
        )
        install.install("p1", target)
        _first_settings = (target / ".claude" / "settings.json").read_text()
        first_claude_md = (target / ".claude" / "CLAUDE.md").read_text()

        install.install("p1", target)
        _second_settings = (target / ".claude" / "settings.json").read_text()
        second_claude_md = (target / ".claude" / "CLAUDE.md").read_text()

        # .claude/CLAUDE.md is always overwritten, should be same
        assert first_claude_md == second_claude_md
        # Symlinks should still be valid
        assert (target / ".claude" / "skills" / "spec").is_symlink()
        assert (target / ".claude" / "hooks" / "notification").is_symlink()

    def test_hooks_reset_on_reinstall(self, fake_repo, tmp_path):
        """Hooks are reset on each install to avoid stale entries."""
        target = tmp_path / "project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={"skills": [], "hooks": [], "pipelines": [], "external": []},
            settings={"hooks": {"Stop": [{"command": "a"}]}},
        )
        install.install("p1", target)
        settings1 = json.loads((target / ".claude" / "settings.json").read_text())
        assert len(settings1["hooks"]["Stop"]) == 1

        # Second install resets hooks (no accumulation)
        install.install("p1", target)
        settings2 = json.loads((target / ".claude" / "settings.json").read_text())
        assert len(settings2["hooks"]["Stop"]) == 1

    def test_target_doesnt_exist_yet(self, fake_repo, tmp_path):
        """Install creates .claude dir even if target has no .claude yet."""
        target = tmp_path / "fresh-project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={"skills": [], "hooks": [], "pipelines": [], "external": []},
            settings={"hooks": {}},
        )
        install.install("p1", target)
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
        content = "{{include:presets/kb/instructions/saving.md}}\n{{include:common/skills.md}}"
        names = install.extract_common_names_from_template(content)
        assert names == ["skills"]

    def test_empty_content(self):
        assert install.extract_common_names_from_template("") == []


# ===================================================================
# Manifest common and instructions
# ===================================================================


class TestManifestCommonAndInstructions:
    """Integration tests for common and instructions manifest keys."""

    def test_common_sections_appended(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_common(fake_repo["common"], "skills", "## Skills\nUse skills.")
        make_common(fake_repo["common"], "git", "## Git\nCommit rules.")
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": [],
                "hooks": [],
                "pipelines": [],
                "external": [],
                "common": ["skills", "git"],
            },
            settings={"hooks": {}},
            claude_md="# My Preset",
        )
        install.install("p1", target)
        content = (target / ".claude" / "CLAUDE.md").read_text()
        assert content.startswith("# My Preset")
        assert "## Skills" in content
        assert "## Git" in content

    def test_instructions_appended_before_common(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_common(fake_repo["common"], "git", "## Git\nCommit rules.")
        make_instruction(
            fake_repo["presets"], "p1", "saving", "## Saving\nSave notes."
        )
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": [],
                "hooks": [],
                "pipelines": [],
                "external": [],
                "instructions": ["saving"],
                "common": ["git"],
            },
            settings={"hooks": {}},
            claude_md="# KB Mode",
        )
        install.install("p1", target)
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
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": ["orchestrator"],
                "hooks": [],
                "pipelines": [],
                "external": [],
                "common": ["orchestration"],
            },
            settings={"hooks": {}},
            claude_md="# Dev",
        )
        install.install("p1", target)
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
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": ["todo"],
                "hooks": [],
                "pipelines": [],
                "external": [],
                "common": ["orchestration"],
            },
            settings={"hooks": {}},
            claude_md="# Dev",
        )
        with pytest.raises(SystemExit):
            install.install("p1", target)

    def test_missing_instruction_file_raises(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": [],
                "hooks": [],
                "pipelines": [],
                "external": [],
                "instructions": ["nonexistent"],
            },
            settings={"hooks": {}},
            claude_md="# Dev",
        )
        with pytest.raises(FileNotFoundError):
            install.install("p1", target)

    def test_missing_common_file_fails_install(self, fake_repo, tmp_path):
        target = tmp_path / "project"
        target.mkdir()
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": [],
                "hooks": [],
                "pipelines": [],
                "external": [],
                "common": ["nonexistent"],
            },
            settings={"hooks": {}},
            claude_md="# Dev",
        )
        with pytest.raises(SystemExit):
            install.install("p1", target)

    def test_collect_components_includes_common_and_instructions(self, fake_repo):
        make_preset(
            fake_repo["presets"],
            "p1",
            manifest={
                "skills": ["spec"],
                "hooks": [],
                "pipelines": [],
                "external": [],
                "instructions": ["saving", "linking"],
                "common": ["skills", "git"],
            },
        )
        result = install.collect_components("p1")
        assert result["instructions"] == ["saving", "linking"]
        assert result["common"] == ["skills", "git"]
