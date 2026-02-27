#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""
Transcribe audio files using OpenRouter API with Gemini Flash.

Usage:
    transcribe_api.py <audio_file> [options]

Arguments:
    audio_file      Path to audio file (mp3, wav, m4a, etc.)

Options:
    --model=MODEL   Model to use (default: google/gemini-3-flash-preview)
    --lang=LANG     Language hint (e.g., 'ru', 'en')
    --timestamps    Request timestamps in output
    --output=PATH   Output file (default: tmp/<filename>.txt)

Environment:
    OPENROUTER_API_KEY  Required.

Note: Files over 18MB are automatically chunked (requires ffmpeg).

Examples:
    transcribe_api.py audio.mp3
    transcribe_api.py audio.mp3 --lang=ru
    transcribe_api.py audio.mp3 --timestamps
"""

import base64
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx


OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3-flash-preview"
MAX_FILE_SIZE_MB = 18


def find_tmp_dir(start: Path) -> Path:
    """Find tmp directory."""
    current = start.resolve()
    while current != current.parent:
        if (current / "CLAUDE.md").exists():
            return current / "tmp"
        current = current.parent
    return Path.cwd() / "tmp"


def parse_args(args: list[str]) -> dict:
    """Parse command line arguments."""
    result = {
        "audio_file": None,
        "model": DEFAULT_MODEL,
        "lang": None,
        "timestamps": False,
        "output": None,
    }

    for arg in args:
        if arg.startswith("--model="):
            result["model"] = arg.split("=", 1)[1]
        elif arg.startswith("--lang="):
            result["lang"] = arg.split("=", 1)[1]
        elif arg.startswith("--output="):
            result["output"] = arg.split("=", 1)[1]
        elif arg == "--timestamps":
            result["timestamps"] = True
        elif not arg.startswith("-") and result["audio_file"] is None:
            result["audio_file"] = arg

    return result


def get_mime_type(path: Path) -> str:
    """Get MIME type for audio file."""
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type:
        return mime_type
    ext_map = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
        ".webm": "audio/webm",
    }
    return ext_map.get(path.suffix.lower(), "audio/mpeg")


def get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def split_audio(audio_path: Path, chunk_duration: int, tmp_dir: Path) -> list[Path]:
    """Split audio into chunks using ffmpeg."""
    chunks = []
    duration = get_audio_duration(audio_path)
    num_chunks = int(duration // chunk_duration) + 1

    print(
        f"Splitting into {num_chunks} chunks ({chunk_duration}s each)...",
        file=sys.stderr,
    )

    for i in range(num_chunks):
        start = i * chunk_duration
        chunk_path = tmp_dir / f"chunk_{i:03d}.mp3"

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(audio_path),
                "-ss",
                str(start),
                "-t",
                str(chunk_duration),
                "-c",
                "copy",
                str(chunk_path),
            ],
            capture_output=True,
        )

        if chunk_path.exists() and chunk_path.stat().st_size > 0:
            chunks.append(chunk_path)

    return chunks


def transcribe_chunk(
    audio_path: Path,
    model: str,
    language: str | None,
    timestamps: bool,
    api_key: str,
    chunk_num: int | None = None,
) -> str:
    """Transcribe a single audio chunk using OpenRouter API."""
    audio_bytes = audio_path.read_bytes()
    audio_b64 = base64.standard_b64encode(audio_bytes).decode("utf-8")
    mime_type = get_mime_type(audio_path)

    file_size_mb = len(audio_bytes) / (1024 * 1024)
    chunk_info = f" (chunk {chunk_num})" if chunk_num is not None else ""
    print(f"  Sending {file_size_mb:.1f} MB{chunk_info}...", file=sys.stderr)

    prompt_parts = ["Transcribe this audio file accurately."]
    if language:
        prompt_parts.append(f"The audio is in {language}.")
    if timestamps:
        prompt_parts.append(
            "Include timestamps in format [MM:SS] at the start of each paragraph."
        )
    prompt_parts.append("Output only the transcription text.")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": " ".join(prompt_parts)},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{audio_b64}"},
                },
            ],
        }
    ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 100000,
    }

    with httpx.Client(timeout=600.0) as client:
        response = client.post(OPENROUTER_API_URL, headers=headers, json=payload)

    if response.status_code != 200:
        print(f"API Error ({response.status_code}): {response.text}", file=sys.stderr)
        sys.exit(1)

    result = response.json()
    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0]["message"]["content"].strip()
    else:
        print(f"Unexpected response: {result}", file=sys.stderr)
        sys.exit(1)


def transcribe_with_api(
    audio_path: Path, model: str, language: str | None, timestamps: bool, api_key: str
) -> str:
    """Transcribe audio, chunking if necessary."""
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    print(f"Processing {audio_path.name} ({file_size_mb:.1f} MB)...", file=sys.stderr)

    if file_size_mb <= MAX_FILE_SIZE_MB:
        return transcribe_chunk(audio_path, model, language, timestamps, api_key)

    if not shutil.which("ffmpeg"):
        print("Error: ffmpeg required for files over 18MB", file=sys.stderr)
        sys.exit(1)

    duration = get_audio_duration(audio_path)
    bytes_per_second = audio_path.stat().st_size / duration
    chunk_duration = int((MAX_FILE_SIZE_MB * 1024 * 1024) / bytes_per_second)
    chunk_duration = max(60, min(chunk_duration, 600))

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        chunks = split_audio(audio_path, chunk_duration, tmp_path)

        transcripts = []
        for i, chunk_path in enumerate(chunks):
            text = transcribe_chunk(
                chunk_path, model, language, timestamps, api_key, i + 1
            )
            transcripts.append(text)

    return "\n\n".join(transcripts)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    args = parse_args(sys.argv[1:])

    if not args["audio_file"]:
        print("Error: No audio file specified", file=sys.stderr)
        sys.exit(1)

    audio_path = Path(args["audio_file"]).resolve()
    if not audio_path.exists():
        print(f"Error: File not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    text = transcribe_with_api(
        audio_path,
        model=args["model"],
        language=args["lang"],
        timestamps=args["timestamps"],
        api_key=api_key,
    )

    if args["output"]:
        output_path = Path(args["output"])
    else:
        tmp_dir = find_tmp_dir(audio_path)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        output_path = tmp_dir / f"{audio_path.stem}.txt"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text)

    print(f"Saved to: {output_path}", file=sys.stderr)
    print(output_path)


if __name__ == "__main__":
    main()
