"""Tests for transcribe and transcribe_api scripts."""

import base64
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Import script modules by manipulating sys.path
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
TRANSCRIBE_DIR = REPO_ROOT / "skills" / "transcribe" / "scripts"

sys.path.insert(0, str(TRANSCRIBE_DIR))

import transcribe  # noqa: E402
import transcribe_api  # noqa: E402


# ===================================================================
# transcribe.py tests
# ===================================================================


class TestParseArgs:
    """Test argument parsing for local transcription."""

    def test_audio_file_only(self):
        result = transcribe.parse_args(["audio.mp3"])
        assert result["audio_file"] == "audio.mp3"
        assert result["model"] == "large-v3"
        assert result["lang"] is None
        assert result["device"] == "auto"
        assert result["timestamps"] is False
        assert result["output"] is None

    def test_all_options(self):
        result = transcribe.parse_args([
            "recording.wav",
            "--model=medium",
            "--lang=ru",
            "--device=cpu",
            "--timestamps",
            "--output=/tmp/out.txt",
        ])
        assert result["audio_file"] == "recording.wav"
        assert result["model"] == "medium"
        assert result["lang"] == "ru"
        assert result["device"] == "cpu"
        assert result["timestamps"] is True
        assert result["output"] == "/tmp/out.txt"

    def test_no_arguments(self):
        result = transcribe.parse_args([])
        assert result["audio_file"] is None

    def test_unknown_flags_ignored(self):
        result = transcribe.parse_args(["--unknown=val", "file.mp3"])
        assert result["audio_file"] == "file.mp3"

    def test_first_positional_wins(self):
        result = transcribe.parse_args(["first.mp3", "second.mp3"])
        assert result["audio_file"] == "first.mp3"


class TestFormatTimestamp:
    """Test timestamp formatting."""

    def test_seconds_only(self):
        assert transcribe.format_timestamp(45.0) == "00:45"

    def test_minutes_and_seconds(self):
        assert transcribe.format_timestamp(125.0) == "02:05"

    def test_hours(self):
        assert transcribe.format_timestamp(3661.0) == "01:01:01"

    def test_zero(self):
        assert transcribe.format_timestamp(0.0) == "00:00"

    def test_fractional_seconds(self):
        # Fractional part should be truncated (int)
        assert transcribe.format_timestamp(59.9) == "00:59"

    def test_exact_hour(self):
        assert transcribe.format_timestamp(3600.0) == "01:00:00"


class TestFindTmpDir:
    """Test tmp directory resolution."""

    def test_finds_claude_md(self, tmp_path):
        # Create a nested structure with CLAUDE.md at the project root
        project = tmp_path / "project"
        project.mkdir()
        (project / "CLAUDE.md").write_text("")
        subdir = project / "sub" / "deep"
        subdir.mkdir(parents=True)

        result = transcribe.find_tmp_dir(subdir)
        assert result == project / "tmp"

    def test_falls_back_to_cwd(self, tmp_path):
        # No CLAUDE.md anywhere above
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        result = transcribe.find_tmp_dir(deep)
        assert result == Path.cwd() / "tmp"


class TestTranscribeFunction:
    """Test the transcribe function with mocked WhisperModel."""

    def _make_segment(self, text, start=0.0, end=1.0):
        seg = MagicMock()
        seg.text = text
        seg.start = start
        seg.end = end
        return seg

    @patch("transcribe.WhisperModel", create=True)
    def test_basic_transcription(self, mock_whisper_cls):
        segments = [
            self._make_segment(" Hello world. ", 0.0, 2.5),
            self._make_segment(" Second line. ", 2.5, 5.0),
        ]
        info = MagicMock()
        info.language = "en"
        info.language_probability = 0.98
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter(segments), info)
        mock_whisper_cls.return_value = mock_model

        with patch.dict("sys.modules", {"faster_whisper": MagicMock(WhisperModel=mock_whisper_cls)}):
            result = transcribe.transcribe(
                Path("/fake/audio.mp3"),
                model_size="base",
                language=None,
                device="cpu",
                timestamps=False,
            )

        assert result == "Hello world.\nSecond line."

    @patch("transcribe.WhisperModel", create=True)
    def test_transcription_with_timestamps(self, mock_whisper_cls):
        segments = [
            self._make_segment(" Hello. ", 0.0, 30.0),
            self._make_segment(" World. ", 65.0, 90.0),
        ]
        info = MagicMock()
        info.language = "en"
        info.language_probability = 0.95
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter(segments), info)
        mock_whisper_cls.return_value = mock_model

        with patch.dict("sys.modules", {"faster_whisper": MagicMock(WhisperModel=mock_whisper_cls)}):
            result = transcribe.transcribe(
                Path("/fake/audio.mp3"),
                model_size="base",
                language="en",
                device="cpu",
                timestamps=True,
            )

        assert "[00:00 -> 00:30] Hello." in result
        assert "[01:05 -> 01:30] World." in result

    @patch("transcribe.WhisperModel", create=True)
    def test_device_auto_without_torch(self, mock_whisper_cls):
        info = MagicMock()
        info.language = "en"
        info.language_probability = 0.99
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), info)
        mock_whisper_cls.return_value = mock_model

        # Simulate torch not available
        with patch.dict("sys.modules", {
            "faster_whisper": MagicMock(WhisperModel=mock_whisper_cls),
            "torch": None,
        }):
            transcribe.transcribe(
                Path("/fake/audio.mp3"),
                model_size="tiny",
                language=None,
                device="auto",
                timestamps=False,
            )

        # Should have been called with cpu and int8
        mock_whisper_cls.assert_called_with("tiny", device="cpu", compute_type="int8")

    @patch("transcribe.WhisperModel", create=True)
    def test_device_cuda(self, mock_whisper_cls):
        info = MagicMock()
        info.language = "en"
        info.language_probability = 0.99
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), info)
        mock_whisper_cls.return_value = mock_model

        with patch.dict("sys.modules", {"faster_whisper": MagicMock(WhisperModel=mock_whisper_cls)}):
            transcribe.transcribe(
                Path("/fake/audio.mp3"),
                model_size="large-v3",
                language=None,
                device="cuda",
                timestamps=False,
            )

        mock_whisper_cls.assert_called_with("large-v3", device="cuda", compute_type="float16")

    @patch("transcribe.WhisperModel", create=True)
    def test_empty_segments(self, mock_whisper_cls):
        info = MagicMock()
        info.language = "en"
        info.language_probability = 0.9
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), info)
        mock_whisper_cls.return_value = mock_model

        with patch.dict("sys.modules", {"faster_whisper": MagicMock(WhisperModel=mock_whisper_cls)}):
            result = transcribe.transcribe(
                Path("/fake/audio.mp3"),
                model_size="base",
                language=None,
                device="cpu",
                timestamps=False,
            )

        assert result == ""


class TestMainLocal:
    """Test main() for local transcription."""

    def test_no_args_exits(self):
        with patch.object(sys, "argv", ["transcribe.py"]):
            with pytest.raises(SystemExit) as exc_info:
                transcribe.main()
            assert exc_info.value.code == 1

    def test_help_flag(self):
        with patch.object(sys, "argv", ["transcribe.py", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                transcribe.main()
            assert exc_info.value.code == 0

    def test_missing_audio_file(self, tmp_path):
        missing = tmp_path / "nonexistent.mp3"
        with patch.object(sys, "argv", ["transcribe.py", str(missing)]):
            with pytest.raises(SystemExit) as exc_info:
                transcribe.main()
            assert exc_info.value.code == 1

    def test_no_audio_file_arg(self):
        with patch.object(sys, "argv", ["transcribe.py", "--model=base"]):
            with pytest.raises(SystemExit) as exc_info:
                transcribe.main()
            assert exc_info.value.code == 1

    @patch("transcribe.transcribe")
    def test_successful_transcription_default_output(self, mock_transcribe, tmp_path):
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"fake audio data")

        # Create CLAUDE.md so find_tmp_dir resolves to tmp_path/tmp
        (tmp_path / "CLAUDE.md").write_text("")

        mock_transcribe.return_value = "Hello world"

        with patch.object(sys, "argv", ["transcribe.py", str(audio)]):
            transcribe.main()

        output_file = tmp_path / "tmp" / "test.txt"
        assert output_file.exists()
        assert output_file.read_text() == "Hello world"

    @patch("transcribe.transcribe")
    def test_successful_transcription_custom_output(self, mock_transcribe, tmp_path):
        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"fake audio data")
        output = tmp_path / "output" / "result.txt"

        mock_transcribe.return_value = "Transcribed text"

        with patch.object(sys, "argv", ["transcribe.py", str(audio), f"--output={output}"]):
            transcribe.main()

        assert output.exists()
        assert output.read_text() == "Transcribed text"


# ===================================================================
# transcribe_api.py tests
# ===================================================================


class TestParseArgsApi:
    """Test argument parsing for API transcription."""

    def test_audio_file_only(self):
        result = transcribe_api.parse_args(["audio.mp3"])
        assert result["audio_file"] == "audio.mp3"
        assert result["model"] == transcribe_api.DEFAULT_MODEL
        assert result["lang"] is None
        assert result["timestamps"] is False
        assert result["output"] is None

    def test_all_options(self):
        result = transcribe_api.parse_args([
            "recording.wav",
            "--model=google/gemini-pro",
            "--lang=en",
            "--timestamps",
            "--output=/tmp/out.txt",
        ])
        assert result["audio_file"] == "recording.wav"
        assert result["model"] == "google/gemini-pro"
        assert result["lang"] == "en"
        assert result["timestamps"] is True
        assert result["output"] == "/tmp/out.txt"

    def test_no_arguments(self):
        result = transcribe_api.parse_args([])
        assert result["audio_file"] is None

    def test_first_positional_wins(self):
        result = transcribe_api.parse_args(["a.mp3", "b.mp3"])
        assert result["audio_file"] == "a.mp3"


class TestGetMimeType:
    """Test MIME type detection."""

    def test_mp3(self, tmp_path):
        assert "audio" in transcribe_api.get_mime_type(Path("test.mp3"))

    def test_wav(self):
        mime = transcribe_api.get_mime_type(Path("test.wav"))
        assert "audio" in mime or "x-wav" in mime

    def test_m4a(self):
        mime = transcribe_api.get_mime_type(Path("test.m4a"))
        assert "audio" in mime or "mp4" in mime

    def test_unknown_extension(self):
        mime = transcribe_api.get_mime_type(Path("test.zzzzunknown"))
        # Falls back to audio/mpeg
        assert mime == "audio/mpeg"

    def test_ogg(self):
        mime = transcribe_api.get_mime_type(Path("test.ogg"))
        assert "ogg" in mime

    def test_flac(self):
        mime = transcribe_api.get_mime_type(Path("test.flac"))
        assert "flac" in mime


class TestGetAudioDuration:
    """Test ffprobe-based duration detection."""

    @patch("transcribe_api.subprocess.run")
    def test_returns_duration(self, mock_run):
        mock_run.return_value = MagicMock(stdout="123.45\n")
        result = transcribe_api.get_audio_duration(Path("/fake/audio.mp3"))
        assert result == 123.45

    @patch("transcribe_api.subprocess.run")
    def test_calls_ffprobe(self, mock_run):
        mock_run.return_value = MagicMock(stdout="60.0\n")
        transcribe_api.get_audio_duration(Path("/fake/audio.mp3"))
        args = mock_run.call_args[0][0]
        assert args[0] == "ffprobe"
        assert "/fake/audio.mp3" in args


class TestSplitAudio:
    """Test audio chunking with ffmpeg."""

    @patch("transcribe_api.subprocess.run")
    @patch("transcribe_api.get_audio_duration")
    def test_creates_chunks(self, mock_duration, mock_run, tmp_path):
        mock_duration.return_value = 250.0  # 250 seconds

        def fake_ffmpeg(cmd, **kwargs):
            # Create the output chunk file
            output_path = cmd[-1]
            Path(output_path).write_bytes(b"fake chunk data")
            return MagicMock()

        mock_run.side_effect = fake_ffmpeg

        chunks = transcribe_api.split_audio(Path("/fake/audio.mp3"), 100, tmp_path)
        assert len(chunks) == 3  # 250/100 + 1 = 3

    @patch("transcribe_api.subprocess.run")
    @patch("transcribe_api.get_audio_duration")
    def test_skips_empty_chunks(self, mock_duration, mock_run, tmp_path):
        mock_duration.return_value = 100.0

        # Don't create any output files (simulating ffmpeg failure)
        mock_run.return_value = MagicMock()

        chunks = transcribe_api.split_audio(Path("/fake/audio.mp3"), 100, tmp_path)
        assert len(chunks) == 0


class TestTranscribeChunk:
    """Test single-chunk API transcription."""

    @patch("transcribe_api.httpx.Client")
    def test_successful_transcription(self, mock_client_cls, tmp_path):
        audio = tmp_path / "chunk.mp3"
        audio.write_bytes(b"fake audio bytes")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": " Hello world. "}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = transcribe_api.transcribe_chunk(
            audio, model="test-model", language=None,
            timestamps=False, api_key="test-key",
        )
        assert result == "Hello world."

    @patch("transcribe_api.httpx.Client")
    def test_api_error_exits(self, mock_client_cls, tmp_path):
        audio = tmp_path / "chunk.mp3"
        audio.write_bytes(b"fake audio bytes")

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            transcribe_api.transcribe_chunk(
                audio, model="test-model", language=None,
                timestamps=False, api_key="test-key",
            )
        assert exc_info.value.code == 1

    @patch("transcribe_api.httpx.Client")
    def test_unexpected_response_exits(self, mock_client_cls, tmp_path):
        audio = tmp_path / "chunk.mp3"
        audio.write_bytes(b"fake audio bytes")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "something went wrong"}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        with pytest.raises(SystemExit) as exc_info:
            transcribe_api.transcribe_chunk(
                audio, model="test-model", language=None,
                timestamps=False, api_key="test-key",
            )
        assert exc_info.value.code == 1

    @patch("transcribe_api.httpx.Client")
    def test_request_includes_auth_header(self, mock_client_cls, tmp_path):
        audio = tmp_path / "chunk.mp3"
        audio.write_bytes(b"data")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "text"}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        transcribe_api.transcribe_chunk(
            audio, model="test-model", language=None,
            timestamps=False, api_key="my-secret-key",
        )

        call_kwargs = mock_client.post.call_args
        headers = call_kwargs[1]["headers"] if "headers" in call_kwargs[1] else call_kwargs.kwargs["headers"]
        assert headers["Authorization"] == "Bearer my-secret-key"

    @patch("transcribe_api.httpx.Client")
    def test_request_includes_audio_base64(self, mock_client_cls, tmp_path):
        audio = tmp_path / "chunk.mp3"
        audio_data = b"test audio content"
        audio.write_bytes(audio_data)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "text"}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        transcribe_api.transcribe_chunk(
            audio, model="test-model", language=None,
            timestamps=False, api_key="key",
        )

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs.kwargs["json"]
        content_parts = payload["messages"][0]["content"]
        image_part = content_parts[1]
        expected_b64 = base64.standard_b64encode(audio_data).decode("utf-8")
        assert expected_b64 in image_part["image_url"]["url"]

    @patch("transcribe_api.httpx.Client")
    def test_language_included_in_prompt(self, mock_client_cls, tmp_path):
        audio = tmp_path / "chunk.mp3"
        audio.write_bytes(b"data")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "text"}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        transcribe_api.transcribe_chunk(
            audio, model="test-model", language="ru",
            timestamps=False, api_key="key",
        )

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs.kwargs["json"]
        text_part = payload["messages"][0]["content"][0]["text"]
        assert "ru" in text_part

    @patch("transcribe_api.httpx.Client")
    def test_timestamps_included_in_prompt(self, mock_client_cls, tmp_path):
        audio = tmp_path / "chunk.mp3"
        audio.write_bytes(b"data")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "text"}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        transcribe_api.transcribe_chunk(
            audio, model="test-model", language=None,
            timestamps=True, api_key="key",
        )

        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs.kwargs["json"]
        text_part = payload["messages"][0]["content"][0]["text"]
        assert "timestamp" in text_part.lower()

    @patch("transcribe_api.httpx.Client")
    def test_chunk_num_label(self, mock_client_cls, tmp_path):
        """Chunk number should appear in stderr output."""
        audio = tmp_path / "chunk.mp3"
        audio.write_bytes(b"data")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "text"}}]
        }
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value = mock_client

        # Should not raise; chunk_num is just for logging
        transcribe_api.transcribe_chunk(
            audio, model="test-model", language=None,
            timestamps=False, api_key="key", chunk_num=3,
        )


class TestTranscribeWithApi:
    """Test the high-level transcribe_with_api function."""

    @patch("transcribe_api.transcribe_chunk")
    def test_small_file_no_chunking(self, mock_chunk, tmp_path):
        audio = tmp_path / "small.mp3"
        audio.write_bytes(b"x" * 1000)  # Well under 18MB

        mock_chunk.return_value = "Transcribed text"

        result = transcribe_api.transcribe_with_api(
            audio, model="test-model", language=None,
            timestamps=False, api_key="key",
        )
        assert result == "Transcribed text"
        mock_chunk.assert_called_once()

    @patch("transcribe_api.split_audio")
    @patch("transcribe_api.get_audio_duration")
    @patch("transcribe_api.shutil.which")
    @patch("transcribe_api.transcribe_chunk")
    def test_large_file_chunked(self, mock_chunk, mock_which, mock_duration, mock_split, tmp_path):
        audio = tmp_path / "large.mp3"
        # Create a file larger than 18MB
        audio.write_bytes(b"x" * (19 * 1024 * 1024))

        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_duration.return_value = 600.0  # 10 minutes

        chunk1 = tmp_path / "chunk1.mp3"
        chunk2 = tmp_path / "chunk2.mp3"
        chunk1.write_bytes(b"c1")
        chunk2.write_bytes(b"c2")
        mock_split.return_value = [chunk1, chunk2]

        mock_chunk.side_effect = ["Part one", "Part two"]

        result = transcribe_api.transcribe_with_api(
            audio, model="test-model", language=None,
            timestamps=False, api_key="key",
        )
        assert result == "Part one\n\nPart two"
        assert mock_chunk.call_count == 2

    @patch("transcribe_api.shutil.which")
    def test_large_file_no_ffmpeg_exits(self, mock_which, tmp_path):
        audio = tmp_path / "large.mp3"
        audio.write_bytes(b"x" * (19 * 1024 * 1024))

        mock_which.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            transcribe_api.transcribe_with_api(
                audio, model="test-model", language=None,
                timestamps=False, api_key="key",
            )
        assert exc_info.value.code == 1


class TestFindTmpDirApi:
    """Test tmp directory resolution in API script."""

    def test_finds_claude_md(self, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        (project / "CLAUDE.md").write_text("")
        subdir = project / "sub"
        subdir.mkdir()

        result = transcribe_api.find_tmp_dir(subdir)
        assert result == project / "tmp"

    def test_falls_back_to_cwd(self, tmp_path):
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        result = transcribe_api.find_tmp_dir(deep)
        assert result == Path.cwd() / "tmp"


class TestMainApi:
    """Test main() for API-based transcription."""

    def test_no_args_exits(self):
        with patch.object(sys, "argv", ["transcribe_api.py"]):
            with pytest.raises(SystemExit) as exc_info:
                transcribe_api.main()
            assert exc_info.value.code == 1

    def test_help_flag(self):
        with patch.object(sys, "argv", ["transcribe_api.py", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                transcribe_api.main()
            assert exc_info.value.code == 0

    def test_missing_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with patch.object(sys, "argv", ["transcribe_api.py", "audio.mp3"]):
            with pytest.raises(SystemExit) as exc_info:
                transcribe_api.main()
            assert exc_info.value.code == 1

    def test_missing_audio_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        missing = tmp_path / "nonexistent.mp3"
        with patch.object(sys, "argv", ["transcribe_api.py", str(missing)]):
            with pytest.raises(SystemExit) as exc_info:
                transcribe_api.main()
            assert exc_info.value.code == 1

    def test_no_audio_file_arg(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        with patch.object(sys, "argv", ["transcribe_api.py", "--model=test"]):
            with pytest.raises(SystemExit) as exc_info:
                transcribe_api.main()
            assert exc_info.value.code == 1

    @patch("transcribe_api.transcribe_with_api")
    def test_successful_transcription_default_output(self, mock_transcribe, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"fake audio data")

        # Create CLAUDE.md so find_tmp_dir resolves
        (tmp_path / "CLAUDE.md").write_text("")

        mock_transcribe.return_value = "API transcription result"

        with patch.object(sys, "argv", ["transcribe_api.py", str(audio)]):
            transcribe_api.main()

        output_file = tmp_path / "tmp" / "test.txt"
        assert output_file.exists()
        assert output_file.read_text() == "API transcription result"

    @patch("transcribe_api.transcribe_with_api")
    def test_successful_transcription_custom_output(self, mock_transcribe, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

        audio = tmp_path / "test.mp3"
        audio.write_bytes(b"fake audio data")
        output = tmp_path / "output" / "result.txt"

        mock_transcribe.return_value = "Custom output text"

        with patch.object(sys, "argv", ["transcribe_api.py", str(audio), f"--output={output}"]):
            transcribe_api.main()

        assert output.exists()
        assert output.read_text() == "Custom output text"


class TestApiConstants:
    """Test module-level constants."""

    def test_api_url(self):
        assert "openrouter.ai" in transcribe_api.OPENROUTER_API_URL

    def test_default_model(self):
        assert transcribe_api.DEFAULT_MODEL == "google/gemini-2.0-flash-001"

    def test_max_file_size(self):
        assert transcribe_api.MAX_FILE_SIZE_MB == 18
