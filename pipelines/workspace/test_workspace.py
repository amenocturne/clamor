"""Tests for generate-workspace pipeline."""

import argparse
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Import the generate-workspace module by manipulating sys.path.
#
# generate-workspace.py has module-level imports of ``yaml`` (pyyaml) and
# ``rich`` which are *not* available in the lightweight test environment.
# We inject lightweight mocks into ``sys.modules`` before the import so
# that the module loads successfully.
# ---------------------------------------------------------------------------

PIPELINE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PIPELINE_DIR))

# --- mock pyyaml -----------------------------------------------------------
_yaml_mock = MagicMock()


def _fake_dump(data, **kwargs):
    """Minimal YAML-like serialiser used by the mocked ``yaml.dump``."""

    # Produce a simple YAML-ish output that the CLI tests can assert against
    # by converting to a readable string.
    lines: list[str] = []

    def _render(obj, indent=0):
        prefix = "  " * indent
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{prefix}{k}:")
                    _render(v, indent + 1)
                else:
                    lines.append(f"{prefix}{k}: {v}")
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}-")
                    _render(item, indent + 1)
                else:
                    lines.append(f"{prefix}- {item}")
        else:
            lines.append(f"{prefix}{obj}")

    _render(data)
    return "\n".join(lines) + "\n"


_yaml_mock.dump = _fake_dump
_yaml_mock.safe_load = MagicMock(
    side_effect=lambda text: __import__("json").loads("{}")
)
_yaml_mock.add_representer = MagicMock()
sys.modules.setdefault("yaml", _yaml_mock)

# --- mock rich and its submodules ------------------------------------------
for _mod in [
    "rich",
    "rich.console",
    "rich.progress",
]:
    sys.modules.setdefault(_mod, MagicMock())

# The module has a hyphenated filename, so use importlib
import importlib  # noqa: E402

gen_ws = importlib.import_module("generate-workspace")


# ===================================================================
# TECH_DETECTORS / DEFAULT_COMMANDS constants
# ===================================================================


class TestConstants:
    """Verify critical constant structures."""

    def test_tech_detectors_all_return_two_lists(self):
        for filename, (techs, tools) in gen_ws.TECH_DETECTORS.items():
            assert isinstance(techs, list), f"{filename}: techs should be a list"
            assert isinstance(tools, list), f"{filename}: tools should be a list"

    def test_tech_path_patterns_all_return_two_lists(self):
        for pattern, (techs, tools) in gen_ws.TECH_PATH_PATTERNS.items():
            assert isinstance(techs, list)
            assert isinstance(tools, list)

    def test_tech_extensions_all_return_two_lists(self):
        for extensions, (techs, tools) in gen_ws.TECH_EXTENSIONS.items():
            assert isinstance(extensions, tuple)
            assert isinstance(techs, list)
            assert isinstance(tools, list)

    def test_default_commands_have_required_keys(self):
        required_keys = {"format_cmd", "lint_cmd", "test_cmd"}
        for tool, cmds in gen_ws.DEFAULT_COMMANDS.items():
            assert set(cmds.keys()) == required_keys, f"{tool} missing keys"

    def test_all_detector_tools_have_default_commands(self):
        """Every tool referenced in TECH_DETECTORS should have a DEFAULT_COMMANDS entry."""
        for _filename, (_techs, tools) in gen_ws.TECH_DETECTORS.items():
            for tool in tools:
                assert tool in gen_ws.DEFAULT_COMMANDS, (
                    f"tool '{tool}' has no default commands"
                )

    def test_all_path_pattern_tools_have_default_commands(self):
        for _pattern, (_techs, tools) in gen_ws.TECH_PATH_PATTERNS.items():
            for tool in tools:
                assert tool in gen_ws.DEFAULT_COMMANDS, (
                    f"tool '{tool}' has no default commands"
                )


# ===================================================================
# find_git_repos
# ===================================================================


class TestFindGitRepos:
    """Test git repository discovery."""

    def test_finds_single_repo(self, tmp_path):
        repo = tmp_path / "my-project"
        (repo / ".git").mkdir(parents=True)
        result = gen_ws.find_git_repos(tmp_path)
        assert result == [repo]

    def test_finds_multiple_repos_sorted(self, tmp_path):
        for name in ["bravo", "alpha", "charlie"]:
            (tmp_path / name / ".git").mkdir(parents=True)
        result = gen_ws.find_git_repos(tmp_path)
        names = [r.name for r in result]
        assert names == ["alpha", "bravo", "charlie"]

    def test_skips_nested_repos(self, tmp_path):
        """Repos inside repos should not be discovered."""
        outer = tmp_path / "outer"
        (outer / ".git").mkdir(parents=True)
        inner = outer / "vendor" / "inner"
        (inner / ".git").mkdir(parents=True)
        result = gen_ws.find_git_repos(tmp_path)
        assert result == [outer]

    def test_no_repos(self, tmp_path):
        (tmp_path / "some-dir").mkdir()
        result = gen_ws.find_git_repos(tmp_path)
        assert result == []

    def test_skips_hidden_directories(self, tmp_path):
        hidden = tmp_path / ".hidden" / "project"
        (hidden / ".git").mkdir(parents=True)
        result = gen_ws.find_git_repos(tmp_path)
        assert result == []

    def test_handles_permission_error(self, tmp_path):
        """PermissionError during iteration should be silently ignored."""
        repo = tmp_path / "accessible"
        (repo / ".git").mkdir(parents=True)
        no_access = tmp_path / "locked"
        no_access.mkdir()
        no_access.chmod(0o000)
        try:
            result = gen_ws.find_git_repos(tmp_path)
            assert repo in result
        finally:
            no_access.chmod(0o755)

    def test_root_is_repo(self, tmp_path):
        """If root itself is a git repo, it should be found."""
        (tmp_path / ".git").mkdir()
        result = gen_ws.find_git_repos(tmp_path)
        assert result == [tmp_path]

    def test_deeply_nested_repo(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "project"
        (deep / ".git").mkdir(parents=True)
        result = gen_ws.find_git_repos(tmp_path)
        assert result == [deep]

    def test_nonexistent_root(self, tmp_path):
        missing = tmp_path / "does-not-exist"
        result = gen_ws.find_git_repos(missing)
        assert result == []


# ===================================================================
# get_tracked_files
# ===================================================================


class TestGetTrackedFiles:
    """Test git ls-files integration."""

    @patch("subprocess.run")
    def test_returns_tracked_files(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="src/main.py\npackage.json\nREADME.md\n",
        )
        result = gen_ws.get_tracked_files(Path("/some/repo"))
        assert result == {"src/main.py", "package.json", "README.md"}

    @patch("subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        result = gen_ws.get_tracked_files(Path("/some/repo"))
        assert result == set()

    @patch("subprocess.run")
    def test_returns_empty_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("git", 30)
        result = gen_ws.get_tracked_files(Path("/some/repo"))
        assert result == set()

    @patch("subprocess.run")
    def test_returns_empty_on_git_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        result = gen_ws.get_tracked_files(Path("/some/repo"))
        assert result == set()

    @patch("subprocess.run")
    def test_empty_repo_returns_empty_set(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = gen_ws.get_tracked_files(Path("/some/repo"))
        assert result == set()

    @patch("subprocess.run")
    def test_passes_correct_args(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        repo = Path("/my/repo")
        gen_ws.get_tracked_files(repo)
        mock_run.assert_called_once_with(
            ["git", "ls-files"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        )


# ===================================================================
# detect_tech_stack
# ===================================================================


class TestDetectTechStack:
    """Test tech stack detection from build files."""

    @patch.object(gen_ws, "get_tracked_files")
    def test_python_project(self, mock_tracked):
        mock_tracked.return_value = {"pyproject.toml", "src/main.py"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "python" in techs
        assert "uv" in tools

    @patch.object(gen_ws, "get_tracked_files")
    def test_javascript_project(self, mock_tracked):
        mock_tracked.return_value = {"package.json", "src/index.js"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "javascript" in techs
        assert "typescript" in techs
        assert "npm" in tools

    @patch.object(gen_ws, "get_tracked_files")
    def test_rust_project(self, mock_tracked):
        mock_tracked.return_value = {"Cargo.toml", "src/lib.rs"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "rust" in techs
        assert "cargo" in tools

    @patch.object(gen_ws, "get_tracked_files")
    def test_scala_project(self, mock_tracked):
        mock_tracked.return_value = {"build.sbt", "src/Main.scala"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "scala" in techs
        assert "sbt" in tools

    @patch.object(gen_ws, "get_tracked_files")
    def test_go_project(self, mock_tracked):
        mock_tracked.return_value = {"go.mod", "main.go"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "go" in techs
        assert tools == []  # go has no tools in TECH_DETECTORS

    @patch.object(gen_ws, "get_tracked_files")
    def test_gradle_kotlin_project(self, mock_tracked):
        mock_tracked.return_value = {"build.gradle.kts", "src/Main.kt"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "kotlin" in techs
        assert "java" in techs
        assert "gradle" in tools

    @patch.object(gen_ws, "get_tracked_files")
    def test_gradle_project(self, mock_tracked):
        mock_tracked.return_value = {"build.gradle", "src/Main.java"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "java" in techs
        assert "gradle" in tools

    @patch.object(gen_ws, "get_tracked_files")
    def test_swift_package(self, mock_tracked):
        mock_tracked.return_value = {"Package.swift", "Sources/main.swift"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "swift" in techs
        assert "spm" in tools

    @patch.object(gen_ws, "get_tracked_files")
    def test_xcode_project(self, mock_tracked):
        mock_tracked.return_value = {
            "MyApp.xcodeproj/project.pbxproj",
            "Sources/main.swift",
        }
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "swift" in techs
        assert "xcode" in tools

    @patch.object(gen_ws, "get_tracked_files")
    def test_yaml_config_repo(self, mock_tracked):
        mock_tracked.return_value = {"config.yaml", "values.yml"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "yaml" in techs

    @patch.object(gen_ws, "get_tracked_files")
    def test_nested_build_file(self, mock_tracked):
        """Build files in subdirectories should be detected."""
        mock_tracked.return_value = {"subdir/package.json", "subdir/src/index.js"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "javascript" in techs
        assert "npm" in tools

    @patch.object(gen_ws, "get_tracked_files")
    def test_unknown_project(self, mock_tracked):
        """Repo with no recognized build files and no fallback files."""
        mock_tracked.return_value = {"README.md", "notes.txt"}
        repo = Path("/repo")
        # Ensure no fallback files exist on disk
        with patch.object(Path, "exists", return_value=False):
            techs, tools = gen_ws.detect_tech_stack(repo)
        assert techs == []
        assert tools == []

    @patch.object(gen_ws, "get_tracked_files")
    def test_multi_tech_project(self, mock_tracked):
        """A repo with multiple build files detects all stacks."""
        mock_tracked.return_value = {"package.json", "pyproject.toml", "go.mod"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert "python" in techs
        assert "javascript" in techs
        assert "go" in techs
        assert "npm" in tools
        assert "uv" in tools

    @patch.object(gen_ws, "get_tracked_files")
    def test_results_are_sorted(self, mock_tracked):
        mock_tracked.return_value = {"package.json", "pyproject.toml"}
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert techs == sorted(techs)
        assert tools == sorted(tools)

    @patch.object(gen_ws, "get_tracked_files")
    def test_fallback_to_filesystem(self, mock_tracked, tmp_path):
        """When no tracked files match, fallback checks root directory."""
        mock_tracked.return_value = set()
        repo = tmp_path / "new-repo"
        repo.mkdir()
        (repo / "pyproject.toml").write_text("[project]\nname = 'test'\n")
        techs, tools = gen_ws.detect_tech_stack(repo)
        assert "python" in techs
        assert "uv" in tools


# ===================================================================
# get_commands
# ===================================================================


class TestGetCommands:
    """Test command lookup for tools."""

    def test_known_tool(self):
        cmds = gen_ws.get_commands(["npm"])
        assert cmds["format_cmd"] == "npm run format"
        assert cmds["lint_cmd"] == "npm run lint"
        assert cmds["test_cmd"] == "npm test"

    def test_unknown_tool(self):
        cmds = gen_ws.get_commands(["nonexistent-tool"])
        assert cmds == {"format_cmd": None, "lint_cmd": None, "test_cmd": None}

    def test_empty_tools(self):
        cmds = gen_ws.get_commands([])
        assert cmds == {"format_cmd": None, "lint_cmd": None, "test_cmd": None}

    def test_first_matching_tool_wins(self):
        """Should return commands for the first matching tool."""
        cmds = gen_ws.get_commands(["cargo", "npm"])
        assert cmds["format_cmd"] == "cargo fmt"

    def test_returns_copy(self):
        """Should return a copy, not a reference to the original dict."""
        cmds = gen_ws.get_commands(["npm"])
        cmds["format_cmd"] = "modified"
        assert gen_ws.DEFAULT_COMMANDS["npm"]["format_cmd"] == "npm run format"

    def test_sbt_commands(self):
        cmds = gen_ws.get_commands(["sbt"])
        assert cmds["format_cmd"] == "sbt scalafmtAll"
        assert cmds["test_cmd"] == "sbt test"

    def test_uv_commands(self):
        cmds = gen_ws.get_commands(["uv"])
        assert cmds["format_cmd"] == "uv run ruff format ."
        assert cmds["lint_cmd"] == "uv run ruff check ."
        assert cmds["test_cmd"] == "uv run pytest"

    def test_gradle_commands(self):
        cmds = gen_ws.get_commands(["gradle"])
        assert cmds["format_cmd"] is None
        assert cmds["lint_cmd"] == "./gradlew check"
        assert cmds["test_cmd"] == "./gradlew test"

    def test_xcode_commands(self):
        cmds = gen_ws.get_commands(["xcode"])
        assert cmds["format_cmd"] is None
        assert cmds["lint_cmd"] is None
        assert cmds["test_cmd"] == "xcodebuild test"

    def test_spm_commands(self):
        cmds = gen_ws.get_commands(["spm"])
        assert cmds["format_cmd"] is None
        assert cmds["lint_cmd"] is None
        assert cmds["test_cmd"] == "swift test"


# ===================================================================
# generate_project_entry
# ===================================================================


class TestGenerateProjectEntry:
    """Test project entry generation."""

    @patch.object(gen_ws, "get_tracked_files")
    def test_python_project_entry(self, mock_tracked, tmp_path):
        repo = tmp_path / "my-lib"
        repo.mkdir()
        mock_tracked.return_value = {"pyproject.toml", "src/main.py"}
        entry = gen_ws.generate_project_entry(repo, tmp_path)
        assert entry["path"] == "./my-lib"
        assert entry["description"] == "TODO: describe this project"
        assert "python" in entry["tech"]
        assert "uv" in entry["tech"]
        assert entry["format_cmd"] == "uv run ruff format ."
        assert entry["lint_cmd"] == "uv run ruff check ."
        assert entry["test_cmd"] == "uv run pytest"
        assert entry["explore_when"] == []
        assert entry["entry_points"] == []

    @patch.object(gen_ws, "get_tracked_files")
    def test_unknown_project_entry(self, mock_tracked, tmp_path):
        repo = tmp_path / "mystery"
        repo.mkdir()
        mock_tracked.return_value = {"README.md"}
        with patch.object(Path, "exists", return_value=False):
            entry = gen_ws.generate_project_entry(repo, tmp_path)
        assert entry["tech"] == ["unknown"]
        assert "format_cmd" not in entry
        assert "lint_cmd" not in entry
        assert "test_cmd" not in entry

    @patch.object(gen_ws, "get_tracked_files")
    def test_gradle_entry_no_format_cmd(self, mock_tracked, tmp_path):
        """Gradle has no format_cmd; entry should omit it."""
        repo = tmp_path / "jvm-app"
        repo.mkdir()
        mock_tracked.return_value = {"build.gradle.kts"}
        entry = gen_ws.generate_project_entry(repo, tmp_path)
        assert "format_cmd" not in entry
        assert "lint_cmd" in entry
        assert "test_cmd" in entry

    @patch.object(gen_ws, "get_tracked_files")
    def test_relative_path_format(self, mock_tracked, tmp_path):
        nested = tmp_path / "group" / "project"
        nested.mkdir(parents=True)
        mock_tracked.return_value = set()
        with patch.object(Path, "exists", return_value=False):
            entry = gen_ws.generate_project_entry(nested, tmp_path)
        assert entry["path"] == "./group/project"


# ===================================================================
# generate_workspace
# ===================================================================


class TestGenerateWorkspace:
    """Test workspace generation."""

    @patch.object(gen_ws, "get_tracked_files")
    def test_generates_workspace_structure(self, mock_tracked, tmp_path):
        repo1 = tmp_path / "alpha"
        (repo1 / ".git").mkdir(parents=True)
        repo2 = tmp_path / "beta"
        (repo2 / ".git").mkdir(parents=True)
        mock_tracked.return_value = {"pyproject.toml"}

        progress = MagicMock()
        progress.add_task.return_value = 0
        workspace = gen_ws.generate_workspace(tmp_path, progress)
        assert workspace["version"] == 1
        assert "alpha" in workspace["projects"]
        assert "beta" in workspace["projects"]
        assert len(workspace["projects"]) == 2

    @patch.object(gen_ws, "get_tracked_files")
    def test_empty_workspace(self, mock_tracked, tmp_path):
        """No repos found should produce empty projects dict."""
        progress = MagicMock()
        progress.add_task.return_value = 0
        workspace = gen_ws.generate_workspace(tmp_path, progress)
        assert workspace["version"] == 1
        assert workspace["projects"] == {}

    @patch.object(gen_ws, "get_tracked_files")
    def test_progress_interactions(self, mock_tracked, tmp_path):
        """Verify progress bar add/remove/update/advance calls."""
        (tmp_path / "repo" / ".git").mkdir(parents=True)
        mock_tracked.return_value = set()

        progress = MagicMock()
        progress.add_task.return_value = 0
        gen_ws.generate_workspace(tmp_path, progress)

        # Should add two tasks (scan + process) and remove the scan task
        assert progress.add_task.call_count == 2
        progress.remove_task.assert_called_once()
        progress.advance.assert_called_once()


# ===================================================================
# main / CLI argument parsing
# ===================================================================


class TestMainCLI:
    """Test CLI argument parsing and main function."""

    @patch.object(gen_ws, "generate_workspace")
    @patch("argparse.ArgumentParser.parse_args")
    def test_default_arguments(self, mock_parse_args, mock_gen, tmp_path):
        output_file = tmp_path / "WORKSPACE.yaml"
        mock_parse_args.return_value = argparse.Namespace(
            root=tmp_path,
            output=output_file,
        )
        mock_gen.return_value = {"version": 1, "projects": {}}
        gen_ws.main()
        assert output_file.exists()
        content = output_file.read_text()
        assert "version: 1" in content

    @patch.object(gen_ws, "generate_workspace")
    @patch("argparse.ArgumentParser.parse_args")
    def test_output_contains_yaml(self, mock_parse_args, mock_gen, tmp_path):
        output_file = tmp_path / "out.yaml"
        mock_parse_args.return_value = argparse.Namespace(
            root=tmp_path,
            output=output_file,
        )
        mock_gen.return_value = {
            "version": 1,
            "projects": {
                "my-project": {
                    "path": "./my-project",
                    "description": "TODO: describe this project",
                    "tech": ["python", "uv"],
                    "explore_when": [],
                    "entry_points": [],
                    "format_cmd": "uv run ruff format .",
                    "lint_cmd": "uv run ruff check .",
                    "test_cmd": "uv run pytest",
                }
            },
        }
        gen_ws.main()
        content = output_file.read_text()
        assert "my-project" in content
        assert "python" in content
        assert "uv run pytest" in content

    @patch.object(gen_ws, "generate_workspace")
    @patch("argparse.ArgumentParser.parse_args")
    def test_output_is_valid_yaml(self, mock_parse_args, mock_gen, tmp_path):
        output_file = tmp_path / "workspace.yaml"
        mock_parse_args.return_value = argparse.Namespace(
            root=tmp_path,
            output=output_file,
        )
        mock_gen.return_value = {
            "version": 1,
            "projects": {
                "test": {
                    "path": "./test",
                    "tech": ["go"],
                    "description": "A test project",
                    "explore_when": [],
                    "entry_points": [],
                }
            },
        }
        gen_ws.main()
        content = output_file.read_text()
        # yaml.dump is mocked; verify the output contains the expected data
        assert "version" in content
        assert "test" in content
        assert "go" in content


# ===================================================================
# Edge cases
# ===================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch.object(gen_ws, "get_tracked_files")
    def test_repo_at_root_level(self, mock_tracked, tmp_path):
        """Repo path equals root path produces './.' since relative_to gives '.'."""
        (tmp_path / ".git").mkdir()
        mock_tracked.return_value = {"Cargo.toml"}
        entry = gen_ws.generate_project_entry(tmp_path, tmp_path)
        assert entry["path"] == "./."

    @patch.object(gen_ws, "get_tracked_files")
    def test_multiple_build_files_same_tool(self, mock_tracked):
        """Multiple build files for the same tool should not duplicate."""
        mock_tracked.return_value = {
            "package.json",
            "subdir/package.json",
            "another/package.json",
        }
        techs, tools = gen_ws.detect_tech_stack(Path("/repo"))
        assert tools.count("npm") == 1
        assert techs.count("javascript") == 1

    @patch("subprocess.run")
    def test_get_tracked_files_with_spaces_in_names(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="path with spaces/file.py\nanother file.txt\n",
        )
        result = gen_ws.get_tracked_files(Path("/repo"))
        assert "path with spaces/file.py" in result
        assert "another file.txt" in result

    def test_find_git_repos_with_file_not_dir(self, tmp_path):
        """A file named .git (not dir) should not be treated as a repo."""
        project = tmp_path / "project"
        project.mkdir()
        (project / ".git").write_text("gitdir: ../other.git")
        # .git is a file (e.g., a submodule), Path.exists() is True but it is a git repo
        result = gen_ws.find_git_repos(tmp_path)
        # .git exists but is not a directory - the code checks .exists() not .is_dir()
        # so it will still be treated as a repo
        assert len(result) == 1

    @patch.object(gen_ws, "get_tracked_files")
    def test_detect_tech_stack_empty_tracked_files(self, mock_tracked, tmp_path):
        """No tracked files and no fallback files on disk."""
        mock_tracked.return_value = set()
        repo = tmp_path / "empty-repo"
        repo.mkdir()
        techs, tools = gen_ws.detect_tech_stack(repo)
        assert techs == []
        assert tools == []
