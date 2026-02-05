#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Inject transcript into a source note.

Usage:
    inject-transcript.py <source-note> [--keep]

Arguments:
    source-note     Path to the source note (must have URL in frontmatter)

Options:
    --keep          Keep the tmp transcript file after injection (default: delete)

The script:
1. Reads the source note's frontmatter to get the YouTube URL
2. Extracts video ID from the URL
3. Finds transcript at tmp/<video_id>.txt
4. Replaces {{transcript}} placeholder with the content
5. Deletes the tmp file (unless --keep)

Examples:
    inject-transcript.py sources/youtube/video-title.md
    inject-transcript.py sources/youtube/video-title.md --keep
"""

import re
import sys
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


def extract_source_url(content: str) -> str | None:
    """Extract source URL from frontmatter."""
    match = re.search(r'^source:\s*(.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def format_transcript(raw_text: str) -> str:
    """Format transcript for readability - group into paragraphs."""
    lines = raw_text.strip().split('\n')

    # Group every ~5 lines into a paragraph for readability
    paragraphs = []
    current = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        current.append(line)
        # Create paragraph every 5 lines or at sentence endings
        if len(current) >= 5 or (line.endswith(('.', '?', '!')) and len(current) >= 3):
            paragraphs.append(' '.join(current))
            current = []

    if current:
        paragraphs.append(' '.join(current))

    return '\n\n'.join(paragraphs)


def find_tmp_dir(start: Path) -> Path:
    """Find tmp directory - look for CLAUDE.md or use cwd/tmp."""
    current = start.resolve()
    while current != current.parent:
        if (current / 'CLAUDE.md').exists():
            return current / 'tmp'
        current = current.parent
    return Path.cwd() / 'tmp'


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    source_note_path = sys.argv[1]
    keep_tmp = '--keep' in sys.argv

    note_path = Path(source_note_path).resolve()

    if not note_path.exists():
        print(f"Error: Source note not found: {note_path}", file=sys.stderr)
        sys.exit(1)

    content = note_path.read_text()

    if '{{transcript}}' not in content:
        print(f"Error: No {{{{transcript}}}} placeholder found in {note_path.name}", file=sys.stderr)
        sys.exit(1)

    source_url = extract_source_url(content)
    if not source_url:
        print(f"Error: No 'source:' URL found in frontmatter", file=sys.stderr)
        sys.exit(1)

    video_id = extract_video_id(source_url)
    if not video_id:
        print(f"Error: Could not extract video ID from URL: {source_url}", file=sys.stderr)
        sys.exit(1)

    tmp_dir = find_tmp_dir(note_path)
    transcript_path = tmp_dir / f"{video_id}.txt"

    if not transcript_path.exists():
        print(f"Error: Transcript not found: {transcript_path}", file=sys.stderr)
        print(f"Run: yt-subs.py {source_url}", file=sys.stderr)
        sys.exit(1)

    raw_transcript = transcript_path.read_text()
    formatted = format_transcript(raw_transcript)

    new_content = content.replace('{{transcript}}', formatted)
    note_path.write_text(new_content)

    print(f"Injected transcript into {note_path.name}")

    if not keep_tmp:
        transcript_path.unlink()
        print(f"Deleted {transcript_path.name}")


if __name__ == '__main__':
    main()
