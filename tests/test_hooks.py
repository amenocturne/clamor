"""Tests for link-proxy and save-conversation hooks."""

import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import hook modules by manipulating sys.path
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
LINK_PROXY_DIR = REPO_ROOT / "hooks" / "link-proxy"
SAVE_CONV_DIR = REPO_ROOT / "hooks" / "save-conversation"

sys.path.insert(0, str(LINK_PROXY_DIR))
sys.path.insert(0, str(SAVE_CONV_DIR))

import hook as save_conversation  # noqa: E402
import main as link_proxy  # noqa: E402


# ===================================================================
# link-proxy tests
# ===================================================================


class TestUrlToPlaceholder:
    """Test deterministic URL -> placeholder conversion."""

    def test_basic_url(self):
        url = "https://internal.example.com/path/to/resource"
        placeholder, url_hash = link_proxy.url_to_placeholder(url)
        expected_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
        assert placeholder == f"[InternalLink_internal_{expected_hash}]"
        assert url_hash == expected_hash

    def test_url_without_scheme(self):
        url = "internal.example.com/path"
        placeholder, url_hash = link_proxy.url_to_placeholder(url)
        expected_hash = hashlib.sha256(url.encode()).hexdigest()[:8]
        # Without scheme, first part split by "/" is "internal.example.com"
        # then split by "." gives "internal"
        assert placeholder == f"[InternalLink_internal_{expected_hash}]"

    def test_http_scheme_stripped(self):
        url_http = "http://foo.example.com/bar"
        url_https = "https://foo.example.com/bar"
        _, hash_http = link_proxy.url_to_placeholder(url_http)
        _, hash_https = link_proxy.url_to_placeholder(url_https)
        # Different full URLs => different hashes
        assert hash_http != hash_https

    def test_deterministic(self):
        url = "https://wiki.corp.net/page"
        p1, h1 = link_proxy.url_to_placeholder(url)
        p2, h2 = link_proxy.url_to_placeholder(url)
        assert p1 == p2
        assert h1 == h2

    def test_prefix_fallback_for_numeric_domain(self):
        url = "https://192.168.1.1/admin"
        placeholder, _ = link_proxy.url_to_placeholder(url)
        # prefix is "192" after stripping non-alnum, lowercased
        assert "[InternalLink_192_" in placeholder


class TestBuildUrlPattern:
    """Test domain list -> regex compilation."""

    def test_empty_domains(self):
        assert link_proxy.build_url_pattern([]) is None

    def test_single_domain(self):
        pattern = link_proxy.build_url_pattern(["internal.example.com"])
        assert pattern is not None
        assert pattern.search("https://internal.example.com/page")
        assert pattern.search("http://internal.example.com")
        assert pattern.search("internal.example.com/page")

    def test_no_match_outside_domain(self):
        pattern = link_proxy.build_url_pattern(["internal.example.com"])
        assert pattern.search("https://google.com") is None

    def test_subdomain_matching(self):
        pattern = link_proxy.build_url_pattern(["example.com"])
        assert pattern is not None
        # Should match any subdomain of example.com
        assert pattern.search("https://sub.example.com/path")
        assert pattern.search("deep.sub.example.com")

    def test_multiple_domains(self):
        pattern = link_proxy.build_url_pattern(["internal.corp.net", "wiki.company.org"])
        assert pattern is not None
        assert pattern.search("https://internal.corp.net/page")
        assert pattern.search("https://wiki.company.org/docs")

    def test_invalid_domain_parts(self):
        # Single-part domain has < 2 parts; should not produce a pattern
        assert link_proxy.build_url_pattern(["localhost"]) is None


class TestTransformText:
    """Test URL replacement in text blocks."""

    def setup_method(self):
        self.pattern = link_proxy.build_url_pattern(["example.com"])

    def test_no_urls(self):
        text = "This is plain text with no URLs."
        transformed, mappings = link_proxy.transform_text(text, self.pattern)
        assert transformed == text
        assert mappings == {}

    def test_single_url(self):
        text = "Visit https://internal.example.com/page for info."
        transformed, mappings = link_proxy.transform_text(text, self.pattern)
        assert "https://internal.example.com/page" not in transformed
        assert "[InternalLink_" in transformed
        assert len(mappings) == 1

    def test_multiple_urls(self):
        text = (
            "See https://a.example.com/one and https://b.example.com/two for details."
        )
        transformed, mappings = link_proxy.transform_text(text, self.pattern)
        assert "example.com" not in transformed
        assert len(mappings) == 2

    def test_url_with_port(self):
        text = "Service at https://app.example.com:8080/api"
        transformed, mappings = link_proxy.transform_text(text, self.pattern)
        assert "example.com:8080" not in transformed
        assert len(mappings) == 1

    def test_already_transformed_not_double_processed(self):
        """Placeholders should not be matched by the URL pattern."""
        placeholder = "[InternalLink_internal_abcd1234]"
        text = f"Already masked: {placeholder}"
        transformed, mappings = link_proxy.transform_text(text, self.pattern)
        assert transformed == text
        assert mappings == {}


class TestRestoreText:
    """Test placeholder -> URL restoration."""

    def test_restore_single(self):
        url = "https://internal.example.com/page"
        _, url_hash = link_proxy.url_to_placeholder(url)
        mappings = {url_hash: url}
        text = f"Visit [InternalLink_internal_{url_hash}] for info."
        restored = link_proxy.restore_text(text, mappings)
        assert restored == f"Visit {url} for info."

    def test_restore_no_matching_hash(self):
        text = "Visit [InternalLink_foo_00000000] for info."
        restored = link_proxy.restore_text(text, {"ffffffff": "https://other.com"})
        # Should leave placeholder intact if hash not in mappings
        assert restored == text

    def test_restore_multiple(self):
        url1 = "https://a.example.com/one"
        url2 = "https://b.example.com/two"
        _, h1 = link_proxy.url_to_placeholder(url1)
        _, h2 = link_proxy.url_to_placeholder(url2)
        mappings = {h1: url1, h2: url2}
        text = f"[InternalLink_a_{h1}] and [InternalLink_b_{h2}]"
        restored = link_proxy.restore_text(text, mappings)
        assert url1 in restored
        assert url2 in restored


class TestRoundTrip:
    """Test transform -> restore preserves original text."""

    def test_roundtrip(self):
        pattern = link_proxy.build_url_pattern(["example.com"])
        original = "Check https://wiki.example.com/doc and https://app.example.com/api/v2"
        transformed, mappings = link_proxy.transform_text(original, pattern)
        restored = link_proxy.restore_text(transformed, mappings)
        assert restored == original


class TestSessionTracking:
    """Test session load/save/delete with tmp filesystem."""

    def test_save_and_load_session(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        with patch.object(link_proxy, "SESSIONS_DIR", sessions_dir):
            link_proxy.save_session("sess1", ["/a.txt", "/b.txt"])
            loaded = link_proxy.load_session("sess1")
            assert loaded == ["/a.txt", "/b.txt"]

    def test_load_missing_session(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        with patch.object(link_proxy, "SESSIONS_DIR", sessions_dir):
            loaded = link_proxy.load_session("nonexistent")
            assert loaded == []

    def test_delete_session(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        with patch.object(link_proxy, "SESSIONS_DIR", sessions_dir):
            link_proxy.save_session("sess2", ["/x.txt"])
            link_proxy.delete_session("sess2")
            assert not (sessions_dir / "sess2.json").exists()

    def test_delete_nonexistent_session(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        sessions_dir.mkdir(parents=True)
        with patch.object(link_proxy, "SESSIONS_DIR", sessions_dir):
            # Should not raise
            link_proxy.delete_session("nope")


class TestMappings:
    """Test mappings load/save with tmp filesystem."""

    def test_save_and_load_mappings(self, tmp_path):
        mappings_file = tmp_path / "mappings.json"
        with patch.object(link_proxy, "MAPPINGS_FILE", mappings_file):
            link_proxy.save_mappings({"abc123": "https://example.com"})
            loaded = link_proxy.load_mappings()
            assert loaded == {"abc123": "https://example.com"}

    def test_load_missing_mappings(self, tmp_path):
        mappings_file = tmp_path / "nonexistent.json"
        with patch.object(link_proxy, "MAPPINGS_FILE", mappings_file):
            assert link_proxy.load_mappings() == {}

    def test_load_corrupt_mappings(self, tmp_path):
        mappings_file = tmp_path / "mappings.json"
        mappings_file.write_text("not json!!!")
        with patch.object(link_proxy, "MAPPINGS_FILE", mappings_file):
            assert link_proxy.load_mappings() == {}


class TestLoadDomains:
    """Test domain config loading."""

    def test_load_domains_with_comments(self, tmp_path):
        domains_file = tmp_path / "domains.txt"
        domains_file.write_text("# comment\nexample.com\n\ncorp.net\n")
        with patch.object(link_proxy, "DOMAINS_FILE", domains_file):
            domains = link_proxy.load_domains()
            assert domains == ["example.com", "corp.net"]

    def test_load_domains_missing_file(self, tmp_path):
        domains_file = tmp_path / "nope.txt"
        with patch.object(link_proxy, "DOMAINS_FILE", domains_file):
            assert link_proxy.load_domains() == []


class TestHandleStop:
    """Test the stop hook that restores files."""

    def test_restores_transformed_files(self, tmp_path):
        # Set up a file with a placeholder in it
        url = "https://wiki.example.com/page"
        placeholder, url_hash = link_proxy.url_to_placeholder(url)
        test_file = tmp_path / "code.py"
        test_file.write_text(f'URL = "{placeholder}"')

        sessions_dir = tmp_path / "sessions"
        mappings_file = tmp_path / "mappings.json"

        with (
            patch.object(link_proxy, "SESSIONS_DIR", sessions_dir),
            patch.object(link_proxy, "MAPPINGS_FILE", mappings_file),
        ):
            # Save session and mappings
            link_proxy.save_session("s1", [str(test_file)])
            link_proxy.save_mappings({url_hash: url})

            # Run stop handler
            link_proxy.handle_stop({"session_id": "s1"})

            # File should have original URL
            assert test_file.read_text() == f'URL = "{url}"'
            # Session should be cleaned up
            assert not (sessions_dir / "s1.json").exists()

    def test_stop_no_session_id(self):
        # Should silently return
        link_proxy.handle_stop({})

    def test_stop_empty_session(self, tmp_path):
        sessions_dir = tmp_path / "sessions"
        with patch.object(link_proxy, "SESSIONS_DIR", sessions_dir):
            link_proxy.handle_stop({"session_id": "empty"})


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

    @patch("hook.subprocess.run")
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

    @patch("hook.subprocess.run")
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

    @patch("hook.subprocess.run")
    def test_git_add_fails(self, mock_run):
        from subprocess import CalledProcessError

        mock_run.side_effect = CalledProcessError(1, "git add")
        result = save_conversation.git_commit(
            Path("/project"), "msg", [Path("/project/file.py")]
        )
        assert result is False


class TestFormatMarkdown:
    """Test format_markdown with mocked subprocess."""

    @patch("hook.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert save_conversation.format_markdown(Path("/project")) is True

    @patch("hook.subprocess.run")
    def test_npx_not_found(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        assert save_conversation.format_markdown(Path("/project")) is False

    @patch("hook.subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess

        mock_run.side_effect = subprocess.TimeoutExpired("npx", 60)
        assert save_conversation.format_markdown(Path("/project")) is False


class TestMainNoLog:
    """Test that NO_LOG env var causes early exit."""

    @patch("hook.json.load")
    def test_no_log_env(self, mock_json_load, monkeypatch):
        monkeypatch.setenv("NO_LOG", "1")
        mock_json_load.return_value = {}
        with pytest.raises(SystemExit) as exc_info:
            save_conversation.main()
        assert exc_info.value.code == 0

    @patch("hook.json.load")
    def test_stop_hook_active(self, mock_json_load):
        mock_json_load.return_value = {"stop_hook_active": True}
        with pytest.raises(SystemExit) as exc_info:
            save_conversation.main()
        assert exc_info.value.code == 0

    @patch("hook.json.load")
    def test_missing_transcript_path(self, mock_json_load):
        mock_json_load.return_value = {"stop_hook_active": False}
        with pytest.raises(SystemExit) as exc_info:
            save_conversation.main()
        assert exc_info.value.code == 0


class TestMainTranscriptSaving:
    """Test the main function's transcript saving flow."""

    @patch("hook.git_commit")
    @patch("hook.format_markdown")
    @patch("hook.json.load")
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

    @patch("hook.git_commit")
    @patch("hook.format_markdown")
    @patch("hook.json.load")
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
