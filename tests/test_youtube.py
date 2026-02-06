"""Tests for YouTube skill scripts: yt-subs.py and inject-transcript.py."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import script modules by loading them as modules from file paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
YT_SUBS_PATH = REPO_ROOT / "skills" / "youtube" / "scripts" / "yt-subs.py"
INJECT_PATH = REPO_ROOT / "skills" / "youtube" / "scripts" / "inject-transcript.py"


def _load_module(name: str, path: Path):
    """Load a Python script as a module by file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


yt_subs = _load_module("yt_subs", YT_SUBS_PATH)
inject_transcript = _load_module("inject_transcript", INJECT_PATH)


# ===================================================================
# yt-subs.py tests
# ===================================================================


class TestExtractVideoId:
    """Test YouTube video ID extraction from various URL formats."""

    def test_youtu_be_short_url(self):
        assert yt_subs.extract_video_id("https://youtu.be/NbGuDcRSXlQ") == "NbGuDcRSXlQ"

    def test_youtube_watch_url(self):
        url = "https://www.youtube.com/watch?v=dEqIkdb7Om4"
        assert yt_subs.extract_video_id(url) == "dEqIkdb7Om4"

    def test_youtube_embed_url(self):
        url = "https://www.youtube.com/embed/dEqIkdb7Om4"
        assert yt_subs.extract_video_id(url) == "dEqIkdb7Om4"

    def test_url_with_extra_params(self):
        url = "https://www.youtube.com/watch?v=dEqIkdb7Om4&t=120"
        assert yt_subs.extract_video_id(url) == "dEqIkdb7Om4"

    def test_short_url_with_params(self):
        url = "https://youtu.be/NbGuDcRSXlQ?t=30"
        assert yt_subs.extract_video_id(url) == "NbGuDcRSXlQ"

    def test_invalid_url_returns_none(self):
        assert yt_subs.extract_video_id("https://example.com") is None

    def test_empty_string_returns_none(self):
        assert yt_subs.extract_video_id("") is None

    def test_non_youtube_video_url(self):
        assert yt_subs.extract_video_id("https://vimeo.com/12345678") is None

    def test_url_with_hyphen_and_underscore_in_id(self):
        url = "https://youtu.be/a-B_cD1e2F3"
        assert yt_subs.extract_video_id(url) == "a-B_cD1e2F3"

    def test_id_too_short_returns_none(self):
        url = "https://www.youtube.com/watch?v=short"
        assert yt_subs.extract_video_id(url) is None

    def test_http_scheme(self):
        url = "http://www.youtube.com/watch?v=dEqIkdb7Om4"
        assert yt_subs.extract_video_id(url) == "dEqIkdb7Om4"


class TestCleanVtt:
    """Test VTT subtitle cleaning and deduplication."""

    def test_removes_vtt_header(self):
        vtt = "WEBVTT\nKind: captions\nLanguage: en\n\n00:00:00.000 --> 00:00:02.000\nHello world"
        result = yt_subs.clean_vtt(vtt)
        assert "WEBVTT" not in result
        assert "Kind:" not in result
        assert "Language:" not in result
        assert "Hello world" in result

    def test_removes_timestamps(self):
        vtt = "00:00:01.000 --> 00:00:03.000\nFirst line\n00:00:03.000 --> 00:00:05.000\nSecond line"
        result = yt_subs.clean_vtt(vtt)
        assert "-->" not in result
        assert "First line" in result
        assert "Second line" in result

    def test_removes_music_annotations(self):
        vtt = "00:00:00.000 --> 00:00:05.000\n[Music]\nActual speech"
        result = yt_subs.clean_vtt(vtt)
        assert "[Music]" not in result
        assert "Actual speech" in result

    def test_removes_applause_annotations(self):
        vtt = "00:00:00.000 --> 00:00:05.000\n[Applause]\nThank you"
        result = yt_subs.clean_vtt(vtt)
        assert "[Applause]" not in result
        assert "Thank you" in result

    def test_removes_formatting_tags(self):
        vtt = "00:00:00.000 --> 00:00:02.000\n<00:00:00.000><c>Hello</c> <c>world</c>"
        result = yt_subs.clean_vtt(vtt)
        assert "<" not in result
        assert ">" not in result
        assert "Hello world" in result

    def test_deduplicates_lines(self):
        vtt = (
            "00:00:00.000 --> 00:00:02.000\nHello\n"
            "00:00:01.000 --> 00:00:03.000\nHello\n"
            "00:00:02.000 --> 00:00:04.000\nWorld"
        )
        result = yt_subs.clean_vtt(vtt)
        assert result.count("Hello") == 1
        assert "World" in result

    def test_skips_blank_lines(self):
        vtt = "00:00:00.000 --> 00:00:02.000\nHello\n\n\n00:00:02.000 --> 00:00:04.000\nWorld"
        result = yt_subs.clean_vtt(vtt)
        lines = [l for l in result.split("\n") if l.strip()]
        assert len(lines) == 2

    def test_empty_input(self):
        assert yt_subs.clean_vtt("") == ""

    def test_only_headers_and_timestamps(self):
        vtt = "WEBVTT\nKind: captions\nLanguage: en\n\n00:00:00.000 --> 00:00:02.000\n"
        result = yt_subs.clean_vtt(vtt)
        assert result == ""

    def test_strips_whitespace_from_lines(self):
        vtt = "00:00:00.000 --> 00:00:02.000\n  Hello world  "
        result = yt_subs.clean_vtt(vtt)
        assert result == "Hello world"


class TestExpandLangWithOrig:
    """Test language code expansion with -orig variants."""

    def test_single_lang(self):
        result = yt_subs.expand_lang_with_orig("en")
        assert result == "en,en-orig"

    def test_multiple_langs(self):
        result = yt_subs.expand_lang_with_orig("en,ru")
        assert result == "en,en-orig,ru,ru-orig"

    def test_already_has_orig(self):
        result = yt_subs.expand_lang_with_orig("en-orig")
        # Should not add -orig-orig
        assert result == "en-orig"

    def test_langs_with_spaces(self):
        result = yt_subs.expand_lang_with_orig("en, ru")
        # Strips whitespace from each lang
        assert "en,en-orig" in result
        assert "ru,ru-orig" in result


class TestGetVideoMetadata:
    """Test metadata fetching with mocked subprocess."""

    @patch("yt_subs.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="My Video Title\nMy Channel Name\n",
        )
        title, channel = yt_subs.get_video_metadata("https://youtu.be/abc12345678")
        assert title == "My Video Title"
        assert channel == "My Channel Name"

    @patch("yt_subs.subprocess.run")
    def test_failure_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        title, channel = yt_subs.get_video_metadata("https://youtu.be/abc12345678")
        assert title is None
        assert channel is None

    @patch("yt_subs.subprocess.run")
    def test_only_title_no_channel(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Title Only\n")
        title, channel = yt_subs.get_video_metadata("https://youtu.be/abc12345678")
        assert title == "Title Only"
        assert channel is None


class TestDownloadSubtitles:
    """Test subtitle downloading with mocked subprocess and temp files."""

    @patch("yt_subs.get_video_metadata")
    @patch("yt_subs.subprocess.run")
    def test_success_cleaned(self, mock_run, mock_meta, tmp_path):
        mock_meta.return_value = ("Title", "Channel")
        # Mock yt-dlp writing a VTT file into the temp directory
        vtt_content = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHello world"

        def fake_run(cmd, **kwargs):
            # Write VTT file in the temp dir (find the -o argument)
            for i, arg in enumerate(cmd):
                if arg == "-o":
                    output_template = cmd[i + 1]
                    output_dir = Path(output_template).parent
                    vtt_file = output_dir / "subs.en.vtt"
                    vtt_file.write_text(vtt_content)
                    break
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = fake_run
        content, title, channel = yt_subs.download_subtitles(
            "https://youtu.be/NbGuDcRSXlQ", "en", raw=False
        )
        assert content is not None
        assert "Hello world" in content
        assert "WEBVTT" not in content
        assert title == "Title"
        assert channel == "Channel"

    @patch("yt_subs.get_video_metadata")
    @patch("yt_subs.subprocess.run")
    def test_success_raw(self, mock_run, mock_meta, tmp_path):
        mock_meta.return_value = ("Title", "Channel")
        vtt_content = "WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nHello world"

        def fake_run(cmd, **kwargs):
            for i, arg in enumerate(cmd):
                if arg == "-o":
                    output_dir = Path(cmd[i + 1]).parent
                    (output_dir / "subs.en.vtt").write_text(vtt_content)
                    break
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = fake_run
        content, title, channel = yt_subs.download_subtitles(
            "https://youtu.be/NbGuDcRSXlQ", "en", raw=True
        )
        assert content is not None
        assert "WEBVTT" in content

    def test_invalid_url(self, capsys):
        content, title, channel = yt_subs.download_subtitles(
            "https://example.com/nope", "en", raw=False
        )
        assert content is None
        captured = capsys.readouterr()
        assert "Could not extract video ID" in captured.err

    @patch("yt_subs.get_video_metadata")
    @patch("yt_subs.subprocess.run")
    def test_no_subtitles_found(self, mock_run, mock_meta, capsys):
        mock_meta.return_value = ("Title", "Channel")
        # yt-dlp succeeds but writes no VTT files
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        content, title, channel = yt_subs.download_subtitles(
            "https://youtu.be/NbGuDcRSXlQ", "en", raw=False
        )
        assert content is None
        assert title == "Title"
        captured = capsys.readouterr()
        assert "No subtitles found" in captured.err

    @patch("yt_subs.get_video_metadata")
    @patch("yt_subs.subprocess.run")
    def test_yt_dlp_error(self, mock_run, mock_meta, capsys):
        mock_meta.return_value = ("Title", "Channel")
        mock_run.return_value = MagicMock(returncode=1, stderr="Some fatal error")
        content, title, channel = yt_subs.download_subtitles(
            "https://youtu.be/NbGuDcRSXlQ", "en", raw=False
        )
        assert content is None
        captured = capsys.readouterr()
        assert "Error:" in captured.err


class TestMainYtSubs:
    """Test yt-subs main() argument parsing and output."""

    @patch("yt_subs.download_subtitles")
    def test_help_flag(self, mock_dl):
        with patch.object(sys, "argv", ["yt-subs.py", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                yt_subs.main()
            assert exc_info.value.code == 0

    @patch("yt_subs.download_subtitles")
    def test_no_args(self, mock_dl):
        with patch.object(sys, "argv", ["yt-subs.py"]):
            with pytest.raises(SystemExit) as exc_info:
                yt_subs.main()
            assert exc_info.value.code == 1

    @patch("yt_subs.download_subtitles")
    def test_stdout_output(self, mock_dl, capsys):
        mock_dl.return_value = ("Hello world", "Title", "Channel")
        with patch.object(sys, "argv", ["yt-subs.py", "https://youtu.be/NbGuDcRSXlQ"]):
            yt_subs.main()
        captured = capsys.readouterr()
        assert "Title: Title" in captured.out
        assert "Channel: Channel" in captured.out
        assert "Hello world" in captured.out

    @patch("yt_subs.download_subtitles")
    def test_file_output(self, mock_dl, tmp_path):
        mock_dl.return_value = ("Hello world", "Title", "Channel")
        out_file = tmp_path / "out.txt"
        with patch.object(
            sys, "argv",
            ["yt-subs.py", "https://youtu.be/NbGuDcRSXlQ", f"--output={out_file}"],
        ):
            yt_subs.main()
        content = out_file.read_text()
        assert "Title: Title" in content
        assert "Hello world" in content

    @patch("yt_subs.download_subtitles")
    def test_lang_and_raw_flags(self, mock_dl):
        mock_dl.return_value = ("raw content", None, None)
        with patch.object(
            sys, "argv",
            ["yt-subs.py", "https://youtu.be/NbGuDcRSXlQ", "--lang=ru", "--raw"],
        ):
            yt_subs.main()
        mock_dl.assert_called_once_with("https://youtu.be/NbGuDcRSXlQ", "ru", True)

    @patch("yt_subs.download_subtitles")
    def test_download_failure_exits_1(self, mock_dl):
        mock_dl.return_value = (None, None, None)
        with patch.object(sys, "argv", ["yt-subs.py", "https://youtu.be/NbGuDcRSXlQ"]):
            with pytest.raises(SystemExit) as exc_info:
                yt_subs.main()
            assert exc_info.value.code == 1

    @patch("yt_subs.download_subtitles")
    def test_no_metadata_header(self, mock_dl, capsys):
        mock_dl.return_value = ("content only", None, None)
        with patch.object(sys, "argv", ["yt-subs.py", "https://youtu.be/NbGuDcRSXlQ"]):
            yt_subs.main()
        captured = capsys.readouterr()
        assert "Title:" not in captured.out
        assert "content only" in captured.out


# ===================================================================
# inject-transcript.py tests
# ===================================================================


class TestInjectExtractVideoId:
    """Test video ID extraction in inject-transcript (same logic as yt-subs)."""

    def test_standard_url(self):
        assert inject_transcript.extract_video_id("https://youtu.be/NbGuDcRSXlQ") == "NbGuDcRSXlQ"

    def test_invalid_url(self):
        assert inject_transcript.extract_video_id("https://example.com") is None


class TestExtractSourceUrl:
    """Test source URL extraction from frontmatter."""

    def test_basic_frontmatter(self):
        content = "---\ntitle: Test\nsource: https://youtu.be/NbGuDcRSXlQ\n---\nBody"
        assert inject_transcript.extract_source_url(content) == "https://youtu.be/NbGuDcRSXlQ"

    def test_source_with_extra_whitespace(self):
        content = "source:   https://youtu.be/NbGuDcRSXlQ   \n"
        assert inject_transcript.extract_source_url(content) == "https://youtu.be/NbGuDcRSXlQ"

    def test_no_source_field(self):
        content = "---\ntitle: Test\n---\nBody"
        assert inject_transcript.extract_source_url(content) is None

    def test_source_in_body_not_frontmatter(self):
        # The regex is multiline so it matches anywhere; this is expected behavior
        content = "---\ntitle: Test\n---\nsource: https://youtu.be/abc12345678"
        result = inject_transcript.extract_source_url(content)
        assert result == "https://youtu.be/abc12345678"


class TestFormatTranscript:
    """Test transcript formatting into paragraphs."""

    def test_groups_into_paragraphs(self):
        lines = "\n".join([f"Line {i}" for i in range(10)])
        result = inject_transcript.format_transcript(lines)
        paragraphs = result.split("\n\n")
        assert len(paragraphs) >= 2

    def test_sentence_ending_triggers_paragraph(self):
        # After 3+ lines, a sentence-ending punctuation triggers a paragraph break
        lines = "First line\nSecond line\nThird line ends here.\nFourth line\nFifth line"
        result = inject_transcript.format_transcript(lines)
        paragraphs = result.split("\n\n")
        assert len(paragraphs) >= 2
        assert "Third line ends here." in paragraphs[0]

    def test_empty_input(self):
        assert inject_transcript.format_transcript("") == ""

    def test_blank_lines_skipped(self):
        text = "Line one\n\n\nLine two\n\nLine three"
        result = inject_transcript.format_transcript(text)
        assert "Line one" in result
        assert "Line two" in result
        assert "Line three" in result

    def test_single_line(self):
        result = inject_transcript.format_transcript("Just one line")
        assert result == "Just one line"

    def test_lines_joined_with_space(self):
        lines = "Hello\nworld"
        result = inject_transcript.format_transcript(lines)
        assert "Hello world" in result

    def test_five_lines_form_one_paragraph(self):
        lines = "One\nTwo\nThree\nFour\nFive"
        result = inject_transcript.format_transcript(lines)
        paragraphs = result.split("\n\n")
        assert paragraphs[0] == "One Two Three Four Five"

    def test_six_lines_form_two_paragraphs(self):
        lines = "One\nTwo\nThree\nFour\nFive\nSix"
        result = inject_transcript.format_transcript(lines)
        paragraphs = result.split("\n\n")
        assert len(paragraphs) == 2


class TestFindTmpDir:
    """Test tmp directory discovery logic."""

    def test_finds_tmp_via_claude_md(self, tmp_path):
        # Create a CLAUDE.md in an ancestor directory
        project_root = tmp_path / "project"
        project_root.mkdir()
        (project_root / "CLAUDE.md").write_text("config")
        subdir = project_root / "sub" / "deep"
        subdir.mkdir(parents=True)
        result = inject_transcript.find_tmp_dir(subdir)
        assert result == project_root / "tmp"

    def test_falls_back_to_cwd_tmp(self, tmp_path):
        # No CLAUDE.md anywhere, should fall back to cwd/tmp
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        with patch("inject_transcript.Path.cwd", return_value=tmp_path):
            result = inject_transcript.find_tmp_dir(isolated)
        assert result == tmp_path / "tmp"


class TestInjectTranscriptPlaceholder:
    """Test the core placeholder replacement logic."""

    def test_replaces_placeholder(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\nsource: https://youtu.be/NbGuDcRSXlQ\n---\n\n{{transcript}}")

        # Create CLAUDE.md so find_tmp_dir works
        (tmp_path / "CLAUDE.md").write_text("")
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        transcript_file = tmp_dir / "NbGuDcRSXlQ.txt"
        transcript_file.write_text("Hello\nWorld\nThis is great")

        with patch.object(sys, "argv", ["inject-transcript.py", str(note)]):
            inject_transcript.main()

        result = note.read_text()
        assert "{{transcript}}" not in result
        assert "Hello" in result
        assert "World" in result

    def test_keeps_tmp_file_with_flag(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\nsource: https://youtu.be/NbGuDcRSXlQ\n---\n\n{{transcript}}")

        (tmp_path / "CLAUDE.md").write_text("")
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        transcript_file = tmp_dir / "NbGuDcRSXlQ.txt"
        transcript_file.write_text("Some content")

        with patch.object(sys, "argv", ["inject-transcript.py", str(note), "--keep"]):
            inject_transcript.main()

        assert transcript_file.exists()

    def test_deletes_tmp_file_by_default(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\nsource: https://youtu.be/NbGuDcRSXlQ\n---\n\n{{transcript}}")

        (tmp_path / "CLAUDE.md").write_text("")
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        transcript_file = tmp_dir / "NbGuDcRSXlQ.txt"
        transcript_file.write_text("Some content")

        with patch.object(sys, "argv", ["inject-transcript.py", str(note)]):
            inject_transcript.main()

        assert not transcript_file.exists()

    def test_missing_placeholder_exits(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\nsource: https://youtu.be/NbGuDcRSXlQ\n---\n\nNo placeholder here")

        with patch.object(sys, "argv", ["inject-transcript.py", str(note)]):
            with pytest.raises(SystemExit) as exc_info:
                inject_transcript.main()
            assert exc_info.value.code == 1

    def test_missing_source_url_exits(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\ntitle: Test\n---\n\n{{transcript}}")

        with patch.object(sys, "argv", ["inject-transcript.py", str(note)]):
            with pytest.raises(SystemExit) as exc_info:
                inject_transcript.main()
            assert exc_info.value.code == 1

    def test_nonexistent_note_exits(self, tmp_path):
        fake_path = tmp_path / "nonexistent.md"
        with patch.object(sys, "argv", ["inject-transcript.py", str(fake_path)]):
            with pytest.raises(SystemExit) as exc_info:
                inject_transcript.main()
            assert exc_info.value.code == 1

    def test_missing_transcript_file_exits(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\nsource: https://youtu.be/NbGuDcRSXlQ\n---\n\n{{transcript}}")

        (tmp_path / "CLAUDE.md").write_text("")
        # Do NOT create the tmp transcript file

        with patch.object(sys, "argv", ["inject-transcript.py", str(note)]):
            with pytest.raises(SystemExit) as exc_info:
                inject_transcript.main()
            assert exc_info.value.code == 1

    def test_invalid_video_id_in_source_exits(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\nsource: https://example.com/not-youtube\n---\n\n{{transcript}}")

        with patch.object(sys, "argv", ["inject-transcript.py", str(note)]):
            with pytest.raises(SystemExit) as exc_info:
                inject_transcript.main()
            assert exc_info.value.code == 1

    def test_empty_transcript(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text("---\nsource: https://youtu.be/NbGuDcRSXlQ\n---\n\n{{transcript}}")

        (tmp_path / "CLAUDE.md").write_text("")
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        transcript_file = tmp_dir / "NbGuDcRSXlQ.txt"
        transcript_file.write_text("")

        with patch.object(sys, "argv", ["inject-transcript.py", str(note)]):
            inject_transcript.main()

        result = note.read_text()
        assert "{{transcript}}" not in result

    def test_help_flag(self):
        with patch.object(sys, "argv", ["inject-transcript.py", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                inject_transcript.main()
            assert exc_info.value.code == 0

    def test_no_args(self):
        with patch.object(sys, "argv", ["inject-transcript.py"]):
            with pytest.raises(SystemExit) as exc_info:
                inject_transcript.main()
            assert exc_info.value.code == 1

    def test_preserves_surrounding_content(self, tmp_path):
        note = tmp_path / "note.md"
        note.write_text(
            "---\nsource: https://youtu.be/NbGuDcRSXlQ\n---\n\n"
            "# Title\n\n{{transcript}}\n\n## Notes\n\nSome notes here"
        )

        (tmp_path / "CLAUDE.md").write_text("")
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        (tmp_dir / "NbGuDcRSXlQ.txt").write_text("Transcript text")

        with patch.object(sys, "argv", ["inject-transcript.py", str(note)]):
            inject_transcript.main()

        result = note.read_text()
        assert "# Title" in result
        assert "## Notes" in result
        assert "Some notes here" in result
        assert "Transcript text" in result
        assert "{{transcript}}" not in result
