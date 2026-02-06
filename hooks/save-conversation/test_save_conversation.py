"""Tests for save-conversation hook."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import hook module using importlib to avoid sys.modules collisions with
# other hook.py files (e.g. notification/hook.py).
# ---------------------------------------------------------------------------

HOOK_DIR = Path(__file__).resolve().parent
HOOK_FILE = str(HOOK_DIR / "hook.py")

_spec = importlib.util.spec_from_file_location("save_conversation_hook", HOOK_FILE)
save_conversation = importlib.util.module_from_spec(_spec)
sys.modules["save_conversation_hook"] = save_conversation
_spec.loader.exec_module(save_conversation)


# ===================================================================
# save-conversation tests
# ===================================================================


class TestExtractModifiedFiles:
    """Test file extraction from transcript entries."""

    def test_extracts_write_tool(self, tmp_path):
        test_file = tmp_path / "written.py"
        test_file.write_text("content")
        entries = [
            {
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": str(test_file)},
                        }
                    ]
                }
            }
        ]
        result = save_conversation.extract_modified_files(entries, tmp_path)
        assert Path(str(test_file)) in result

    def test_extracts_edit_tool(self, tmp_path):
        test_file = tmp_path / "edited.py"
        test_file.write_text("content")
        entries = [
            {
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Edit",
                            "input": {"file_path": str(test_file)},
                        }
                    ]
                }
            }
        ]
        result = save_conversation.extract_modified_files(entries, tmp_path)
        assert Path(str(test_file)) in result

    def test_ignores_read_tool(self, tmp_path):
        test_file = tmp_path / "read.py"
        test_file.write_text("content")
        entries = [
            {
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": str(test_file)},
                        }
                    ]
                }
            }
        ]
        result = save_conversation.extract_modified_files(entries, tmp_path)
        assert result == []

    def test_ignores_files_outside_project(self, tmp_path):
        entries = [
            {
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": "/some/other/dir/file.py"},
                        }
                    ]
                }
            }
        ]
        result = save_conversation.extract_modified_files(entries, tmp_path)
        assert result == []

    def test_ignores_nonexistent_files(self, tmp_path):
        entries = [
            {
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": str(tmp_path / "gone.py")},
                        }
                    ]
                }
            }
        ]
        result = save_conversation.extract_modified_files(entries, tmp_path)
        assert result == []

    def test_deduplicates_files(self, tmp_path):
        test_file = tmp_path / "dup.py"
        test_file.write_text("content")
        entries = [
            {
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {"file_path": str(test_file)},
                        },
                        {
                            "type": "tool_use",
                            "name": "Edit",
                            "input": {"file_path": str(test_file)},
                        },
                    ]
                }
            }
        ]
        result = save_conversation.extract_modified_files(entries, tmp_path)
        assert len(result) == 1

    def test_empty_entries(self, tmp_path):
        assert save_conversation.extract_modified_files([], tmp_path) == []

    def test_string_content_skipped(self, tmp_path):
        """Entries with string content (not list) should be skipped."""
        entries = [{"message": {"content": "just a string"}}]
        result = save_conversation.extract_modified_files(entries, tmp_path)
        assert result == []

    def test_missing_file_path_key(self, tmp_path):
        """Tool use block without file_path in input should be skipped."""
        entries = [
            {
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Write",
                            "input": {},
                        }
                    ]
                }
            }
        ]
        result = save_conversation.extract_modified_files(entries, tmp_path)
        assert result == []


class TestGitCommit:
    """Test git_commit function with mocked subprocess."""

    @patch("save_conversation_hook.subprocess.run")
    def test_successful_commit(self, mock_run):
        # git add succeeds, git diff --cached returns 1 (changes staged), git commit succeeds
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=1),  # git diff --cached --quiet => 1 means changes
            MagicMock(returncode=0),  # git commit
        ]
        result = save_conversation.git_commit(
            Path("/project"), "msg", [Path("/project/file.py")]
        )
        assert result is True
        assert mock_run.call_count == 3

    @patch("save_conversation_hook.subprocess.run")
    def test_no_changes_staged(self, mock_run):
        # git add succeeds, git diff --cached returns 0 (no changes)
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=0),  # git diff --cached --quiet => 0 means clean
        ]
        result = save_conversation.git_commit(
            Path("/project"), "msg", [Path("/project/file.py")]
        )
        assert result is False

    def test_no_files(self):
        result = save_conversation.git_commit(Path("/project"), "msg", [])
        assert result is False

    @patch("save_conversation_hook.subprocess.run")
    def test_git_add_fails(self, mock_run):
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, "git add")
        result = save_conversation.git_commit(
            Path("/project"), "msg", [Path("/project/file.py")]
        )
        assert result is False


class TestFormatMarkdown:
    """Test format_markdown with mocked subprocess."""

    @patch("save_conversation_hook.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert save_conversation.format_markdown(Path("/project")) is True

    @patch("save_conversation_hook.subprocess.run")
    def test_npx_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        assert save_conversation.format_markdown(Path("/project")) is False

    @patch("save_conversation_hook.subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("npx", 60)
        assert save_conversation.format_markdown(Path("/project")) is False


class TestMainNoLog:
    """Test that NO_LOG env var causes early exit."""

    @patch("save_conversation_hook.json.load")
    def test_no_log_env(self, mock_json_load, monkeypatch):
        monkeypatch.setenv("NO_LOG", "1")
        mock_json_load.return_value = {}
        with pytest.raises(SystemExit) as exc_info:
            save_conversation.main()
        assert exc_info.value.code == 0

    @patch("save_conversation_hook.json.load")
    def test_stop_hook_active(self, mock_json_load):
        mock_json_load.return_value = {"stop_hook_active": True}
        with pytest.raises(SystemExit) as exc_info:
            save_conversation.main()
        assert exc_info.value.code == 0

    @patch("save_conversation_hook.json.load")
    def test_missing_transcript_path(self, mock_json_load):
        mock_json_load.return_value = {"stop_hook_active": False}
        with pytest.raises(SystemExit) as exc_info:
            save_conversation.main()
        assert exc_info.value.code == 0


class TestMainTranscriptSaving:
    """Test the main function's transcript saving flow."""

    @patch("save_conversation_hook.git_commit")
    @patch("save_conversation_hook.format_markdown")
    @patch("save_conversation_hook.json.load")
    def test_saves_transcript(self, mock_json_load, mock_format, mock_commit, tmp_path, monkeypatch):
        # Clean NO_LOG if set
        monkeypatch.delenv("NO_LOG", raising=False)

        # Create a fake transcript JSONL file
        transcript_file = tmp_path / "transcript.jsonl"
        entry = {
            "leafUuid": "test-session-123",
            "message": {
                "content": "hello"
            }
        }
        transcript_file.write_text(json.dumps(entry) + "\n")

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_dir))

        mock_json_load.return_value = {
            "stop_hook_active": False,
            "transcript_path": str(transcript_file),
        }
        mock_format.return_value = True
        mock_commit.return_value = True

        with pytest.raises(SystemExit) as exc_info:
            save_conversation.main()
        assert exc_info.value.code == 0

        # Should have created a logs directory with a JSON file
        logs_dirs = list((project_dir / "logs").iterdir())
        assert len(logs_dirs) == 1  # one date folder
        json_files = list(logs_dirs[0].glob("*.json"))
        assert len(json_files) == 1
        # Check the saved content
        saved = json.loads(json_files[0].read_text())
        assert len(saved) == 1
        assert saved[0]["leafUuid"] == "test-session-123"

    @patch("save_conversation_hook.git_commit")
    @patch("save_conversation_hook.format_markdown")
    @patch("save_conversation_hook.json.load")
    def test_renames_pending_summaries(self, mock_json_load, mock_format, mock_commit, tmp_path, monkeypatch):
        monkeypatch.delenv("NO_LOG", raising=False)

        transcript_file = tmp_path / "transcript.jsonl"
        entry = {"leafUuid": "sess-abc", "message": {"content": "hi"}}
        transcript_file.write_text(json.dumps(entry) + "\n")

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_dir))

        mock_json_load.return_value = {
            "stop_hook_active": False,
            "transcript_path": str(transcript_file),
        }
        mock_format.return_value = True
        mock_commit.return_value = True

        # Pre-create the logs date folder and a pending summary
        from datetime import datetime
        date_folder = datetime.now().strftime("%Y-%m-%d")
        logs_dir = project_dir / "logs" / date_folder
        logs_dir.mkdir(parents=True)
        pending = logs_dir / "_summary.md"
        pending.write_text("Session: {LOG_ID}\nNotes here.")

        with pytest.raises(SystemExit):
            save_conversation.main()

        # Pending file should be gone
        assert not pending.exists()
        # Should have a renamed file with the session ID substituted
        md_files = list(logs_dir.glob("*.md"))
        assert len(md_files) == 1
        content = md_files[0].read_text()
        assert "sess-abc" in content
        assert "{LOG_ID}" not in content
