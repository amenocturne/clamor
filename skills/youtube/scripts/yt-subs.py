#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Download YouTube subtitles as plain text.

Usage:
    yt-subs.py <url> [--output=PATH] [--lang=LANG] [--raw]

Arguments:
    url         YouTube video URL

Options:
    --output=PATH  Save to file instead of stdout (default: stdout)
    --lang=LANG    Language codes, comma-separated (default: en,ru)
    --raw          Output raw VTT format instead of cleaned text

Examples:
    yt-subs.py https://youtu.be/NbGuDcRSXlQ
    yt-subs.py https://youtu.be/dEqIkdb7Om4 --lang=en,ru
    yt-subs.py "https://www.youtube.com/watch?v=..." --output=transcript.txt
    yt-subs.py "https://www.youtube.com/watch?v=..." --raw
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path


def extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL."""
    patterns = [
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def clean_vtt(content: str) -> str:
    """Convert VTT subtitles to plain readable text."""
    lines = []
    seen = set()

    for line in content.split('\n'):
        # Skip VTT header, timestamps, and metadata
        if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
            continue
        if '-->' in line:
            continue
        if not line.strip():
            continue
        if line.strip().startswith('['):  # [Music], [Applause], etc.
            continue

        # Remove VTT formatting tags like <00:00:00.000><c>word</c>
        clean = re.sub(r'<[^>]+>', '', line)
        clean = clean.strip()

        if not clean:
            continue

        # Deduplicate (VTT often repeats lines)
        if clean not in seen:
            seen.add(clean)
            lines.append(clean)

    return '\n'.join(lines)


def expand_lang_with_orig(lang: str) -> str:
    """Expand language codes to include -orig variants for auto-generated captions."""
    langs = [l.strip() for l in lang.split(',')]
    expanded = []
    for l in langs:
        expanded.append(l)
        # Add -orig variant for auto-generated original language captions
        if not l.endswith('-orig'):
            expanded.append(f"{l}-orig")
    return ','.join(expanded)


def get_video_metadata(url: str) -> tuple[str | None, str | None]:
    """Get video title and channel name using yt-dlp."""
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--print", "title",
        "--print", "channel",
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None, None

    lines = result.stdout.strip().split('\n')
    title = lines[0] if len(lines) > 0 else None
    channel = lines[1] if len(lines) > 1 else None
    return title, channel


def download_subtitles(url: str, lang: str, raw: bool) -> tuple[str | None, str | None, str | None]:
    """Download subtitles using yt-dlp. Returns (content, title, channel)."""
    video_id = extract_video_id(url)
    if not video_id:
        print(f"Error: Could not extract video ID from URL", file=sys.stderr)
        return None, None, None

    # Get video metadata
    title, channel = get_video_metadata(url)

    # Expand languages to include -orig variants (auto-generated originals)
    expanded_lang = expand_lang_with_orig(lang)

    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = str(Path(tmpdir) / "subs")

        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-sub",
            "--write-sub",
            "--ignore-errors",
            f"--sub-lang={expanded_lang}",
            "--sub-format=vtt",
            "-o", output_template,
            url
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            if "Unable to download" not in result.stderr:
                print(f"Error: {result.stderr}", file=sys.stderr)
                return None, title, channel

        # Find downloaded subtitle files
        tmppath = Path(tmpdir)
        vtt_files = list(tmppath.glob("*.vtt"))

        if not vtt_files:
            print("No subtitles found for this video", file=sys.stderr)
            return None, title, channel

        # Read first available subtitle file
        content = vtt_files[0].read_text()

        if raw:
            return content, title, channel
        else:
            return clean_vtt(content), title, channel


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    url = sys.argv[1]
    lang = "en,ru"
    raw = False
    output_path = None

    for arg in sys.argv[2:]:
        if arg.startswith('--lang='):
            lang = arg.split('=', 1)[1]
        elif arg.startswith('--output='):
            output_path = arg.split('=', 1)[1]
        elif arg == '--raw':
            raw = True

    content, title, channel = download_subtitles(url, lang, raw)

    if content is None:
        sys.exit(1)

    # Build metadata header
    header_lines = []
    if title:
        header_lines.append(f"Title: {title}")
    if channel:
        header_lines.append(f"Channel: {channel}")
    header = '\n'.join(header_lines) + '\n\n' if header_lines else ''

    output = header + content

    if output_path:
        Path(output_path).write_text(output)
        print(f"Saved to: {output_path}")
    else:
        print(output)


if __name__ == '__main__':
    main()
