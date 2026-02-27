#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["faster-whisper"]
# ///
"""
Transcribe audio files using Whisper (local, offline).

Usage:
    transcribe.py <audio_file> [options]

Arguments:
    audio_file      Path to audio file (mp3, wav, m4a, etc.)

Options:
    --model=MODEL   Model size (default: large-v3)
                    Options: tiny, base, small, medium, large-v2, large-v3
    --lang=LANG     Language code (default: auto-detect)
    --device=DEV    Device: cuda, cpu, auto (default: auto)
    --timestamps    Include timestamps in output
    --output=PATH   Output file (default: tmp/<filename>.txt)

Examples:
    transcribe.py audio.mp3
    transcribe.py audio.mp3 --model=medium --lang=ru
    transcribe.py audio.mp3 --timestamps
"""

import sys
from pathlib import Path


def find_tmp_dir(start: Path) -> Path:
    """Find tmp directory - look for CLAUDE.md or use cwd/tmp."""
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
        "model": "large-v3",
        "lang": None,
        "device": "auto",
        "timestamps": False,
        "output": None,
    }

    for arg in args:
        if arg.startswith("--model="):
            result["model"] = arg.split("=", 1)[1]
        elif arg.startswith("--lang="):
            result["lang"] = arg.split("=", 1)[1]
        elif arg.startswith("--device="):
            result["device"] = arg.split("=", 1)[1]
        elif arg.startswith("--output="):
            result["output"] = arg.split("=", 1)[1]
        elif arg == "--timestamps":
            result["timestamps"] = True
        elif not arg.startswith("-") and result["audio_file"] is None:
            result["audio_file"] = arg

    return result


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def transcribe(
    audio_path: Path,
    model_size: str,
    language: str | None,
    device: str,
    timestamps: bool,
) -> str:
    """Transcribe audio file using faster-whisper."""
    from faster_whisper import WhisperModel

    if device == "auto":
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
            else:
                device = "cpu"
                compute_type = "int8"
        except ImportError:
            device = "cpu"
            compute_type = "int8"
    elif device == "cuda":
        compute_type = "float16"
    else:
        compute_type = "int8"

    print(
        f"Loading model '{model_size}' on {device} ({compute_type})...", file=sys.stderr
    )
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    print(f"Transcribing {audio_path.name}...", file=sys.stderr)

    segments, info = model.transcribe(
        str(audio_path),
        beam_size=5,
        language=language,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    print(
        f"Detected language: {info.language} ({info.language_probability:.1%})",
        file=sys.stderr,
    )

    lines = []
    for segment in segments:
        if timestamps:
            ts = f"[{format_timestamp(segment.start)} -> {format_timestamp(segment.end)}] "
            lines.append(ts + segment.text.strip())
        else:
            lines.append(segment.text.strip())

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    args = parse_args(sys.argv[1:])

    if not args["audio_file"]:
        print("Error: No audio file specified", file=sys.stderr)
        sys.exit(1)

    audio_path = Path(args["audio_file"]).resolve()
    if not audio_path.exists():
        print(f"Error: File not found: {audio_path}", file=sys.stderr)
        sys.exit(1)

    text = transcribe(
        audio_path,
        model_size=args["model"],
        language=args["lang"],
        device=args["device"],
        timestamps=args["timestamps"],
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
