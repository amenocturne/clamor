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
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
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

    for line in content.split("\n"):
        # Skip VTT header, timestamps, and metadata
        if (
            line.startswith("WEBVTT")
            or line.startswith("Kind:")
            or line.startswith("Language:")
        ):
            continue
        if "-->" in line:
            continue
        if not line.strip():
            continue
        if line.strip().startswith("["):  # [Music], [Applause], etc.
            continue

        # Remove VTT formatting tags like <00:00:00.000><c>word</c>
        clean = re.sub(r"<[^>]+>", "", line)
        clean = clean.strip()

        if not clean:
            continue

        # Deduplicate (VTT often repeats lines)
        if clean not in seen:
            seen.add(clean)
            lines.append(clean)

    return "\n".join(lines)


def expand_lang_with_orig(lang: str) -> str:
    """Expand language codes to include -orig variants for auto-generated captions."""
    langs = [code.strip() for code in lang.split(",")]
    expanded = []
    for code in langs:
        expanded.append(code)
        # Add -orig variant for auto-generated original language captions
        if not code.endswith("-orig"):
            expanded.append(f"{code}-orig")
    return ",".join(expanded)


def get_cookies_args() -> list[str]:
    """Get cookie arguments for yt-dlp (for age-restricted content)."""
    import os
    profile_path = os.path.expanduser("~/Library/Application Support/zen/Profiles")
    if os.path.exists(profile_path):
        return ["--cookies-from-browser", f"firefox:{profile_path}"]
    return []


def get_video_metadata(url: str) -> tuple[str | None, str | None]:
    """Get video title and channel name using yt-dlp."""
    # Try without cookies first
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--remote-components", "ejs:github",
        "--print", "title",
        "--print", "channel",
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # If failed, try with cookies (age-restricted)
    if result.returncode != 0 and get_cookies_args():
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--remote-components", "ejs:github",
            "--print", "title",
            "--print", "channel",
        ] + get_cookies_args() + [url]
        result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        return None, None

    lines = result.stdout.strip().split("\n")
    title = lines[0] if len(lines) > 0 else None
    channel = lines[1] if len(lines) > 1 else None
    return title, channel


def list_available_subtitles(url: str) -> list[str]:
    """Check what subtitles are available for this video."""
    cmd = [
        "yt-dlp",
        "--list-subs",
        "--skip-download",
        url
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Parse output to find available languages
    available = []
    in_subs_section = False
    skip_headers = {"Language", "Name", "Formats", ""}

    for line in result.stdout.split("\n"):
        # Detect section starts
        if "automatic captions" in line.lower() or (
            "subtitles" in line.lower() and "automatic" not in line.lower()
        ):
            in_subs_section = True
            continue

        # Skip non-subtitle lines
        if line.startswith("[") or line.startswith("WARNING"):
            continue

        if in_subs_section:
            # Lines look like: "en            English                vtt, srt, ..."
            parts = line.split()
            if len(parts) >= 2:
                lang_code = parts[0]
                # Skip headers and invalid codes
                if (lang_code not in skip_headers and
                    not lang_code.startswith("-") and
                    len(lang_code) <= 10):  # lang codes are short
                    available.append(lang_code)

    return available


def try_download_subtitles(
    url: str, expanded_lang: str, use_cookies: bool
) -> tuple[list[Path], subprocess.CompletedProcess]:
    """Attempt to download subtitles. Returns (vtt_files, result)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output_template = str(Path(tmpdir) / "subs")

        cmd = [
            "yt-dlp",
            "--skip-download",
            "--remote-components", "ejs:github",
            "--write-auto-sub",
            "--write-sub",
            "--ignore-errors",
            f"--sub-lang={expanded_lang}",
            "--sub-format=vtt",
            "-o",
            output_template,
        ]
        if use_cookies:
            cmd.extend(get_cookies_args())
        cmd.append(url)

        result = subprocess.run(cmd, capture_output=True, text=True)

        tmppath = Path(tmpdir)
        vtt_files = list(tmppath.glob("*.vtt"))

        # If we found files, read them before temp dir is deleted
        contents = []
        for f in vtt_files:
            contents.append((f.name, f.read_text()))

        return contents, result


def download_subtitles(
    url: str, lang: str, raw: bool
) -> tuple[str | None, str | None, str | None]:
    """Download subtitles using yt-dlp. Returns (content, title, channel)."""
    video_id = extract_video_id(url)
    if not video_id:
        print("Error: Could not extract video ID from URL", file=sys.stderr)
        return None, None, None

    # Get video metadata
    title, channel = get_video_metadata(url)

    # Expand languages to include -orig variants (auto-generated originals)
    expanded_lang = expand_lang_with_orig(lang)

    # Try without cookies first (works for most videos)
    vtt_contents, result = try_download_subtitles(url, expanded_lang, use_cookies=False)

    # If no subtitles found, try with cookies (for age-restricted content)
    if not vtt_contents and get_cookies_args():
        print("No subtitles without cookies, trying with cookies (age-restricted?)...",
              file=sys.stderr)
        vtt_contents, result = try_download_subtitles(url, expanded_lang, use_cookies=True)

    # Show errors if download failed
    if result.returncode != 0 and not vtt_contents:
        # Filter out common warnings
        if result.stderr.strip():
            stderr_lines = result.stderr.strip().split("\n")
            errors = [
                line for line in stderr_lines
                if not any(skip in line.upper() for skip in [
                    "WARNING:",
                    "DOWNLOADING WEBPAGE",
                    "DOWNLOADING PLAYER",
                    "DOWNLOADING TV",
                    "DOWNLOADING ANDROID",
                ])
            ]
            if errors:
                print(f"yt-dlp errors:\n{chr(10).join(errors)}", file=sys.stderr)

    if not vtt_contents:
        # Check if subtitles are actually available
        available = list_available_subtitles(url)
        requested_langs = [l.strip() for l in lang.split(",")]

        if available:
            matching = [l for l in available if any(
                l == req or l.startswith(req + "-") or req.startswith(l)
                for req in requested_langs
            )]

            print(f"\n{'='*60}", file=sys.stderr)
            print("SUBTITLE DOWNLOAD FAILED - DEBUG INFO", file=sys.stderr)
            print(f"{'='*60}", file=sys.stderr)
            print(f"Requested languages: {lang}", file=sys.stderr)
            print(f"Expanded to: {expanded_lang}", file=sys.stderr)
            print(f"Available subtitles: {', '.join(available[:20])}" +
                  (f"... (+{len(available)-20} more)" if len(available) > 20 else ""),
                  file=sys.stderr)

            if matching:
                print(f"Matching languages found: {', '.join(matching)}", file=sys.stderr)
                print("\nSubtitles ARE available but download failed!", file=sys.stderr)
                print("Possible causes:", file=sys.stderr)
                print("  1. yt-dlp version outdated (try: yt-dlp -U)", file=sys.stderr)
                print("  2. YouTube API changes", file=sys.stderr)
                print("  3. Network/rate limiting issues", file=sys.stderr)
                print(f"\nDebug: try running manually:", file=sys.stderr)
                print(f"  yt-dlp --skip-download --write-auto-sub --sub-lang={lang} '{url}'", file=sys.stderr)
            else:
                print(f"\nNo matching languages. Try one of: {', '.join(available[:10])}", file=sys.stderr)
            print(f"{'='*60}\n", file=sys.stderr)
        else:
            print("No subtitles available for this video", file=sys.stderr)

        return None, title, channel

    # Use first available subtitle file
    _, content = vtt_contents[0]

    if raw:
        return content, title, channel
    else:
        return clean_vtt(content), title, channel


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    url = sys.argv[1]
    lang = "en,ru"
    raw = False
    output_path = None

    for arg in sys.argv[2:]:
        if arg.startswith("--lang="):
            lang = arg.split("=", 1)[1]
        elif arg.startswith("--output="):
            output_path = arg.split("=", 1)[1]
        elif arg == "--raw":
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
    header = "\n".join(header_lines) + "\n\n" if header_lines else ""

    output = header + content

    if output_path:
        Path(output_path).write_text(output)
        print(f"Saved to: {output_path}")
    else:
        print(output)


if __name__ == "__main__":
    main()
