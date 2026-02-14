---
name: youtube
description: Fetch YouTube transcripts for processing
author: amenocturne
---

# YouTube Transcript Fetcher

Fetch transcripts from YouTube videos.

> All script paths below are relative to this skill folder.

## Usage

When user provides a YouTube URL, download the transcript:

```bash
uv run scripts/yt-subs.py <url> --output=tmp/<video_id>.txt
```

The `tmp/` folder is relative to the project root.

## Scripts

### yt-subs.py

```
yt-subs.py <url> [--output=PATH] [--lang=LANG] [--raw]
```

- `--output`: Save to file (default: stdout)
- `--lang`: Preferred language codes, comma-separated (default: en,ru)
- `--raw`: Output raw VTT format instead of cleaned text

### inject-transcript.py

Injects a previously downloaded transcript into a note that contains a `{{transcript}}` placeholder.

```
inject-transcript.py <note-path> [--keep]
```

- Reads source URL from note's frontmatter
- Finds transcript in `tmp/<video_id>.txt`
- Replaces `{{transcript}}` placeholder with formatted content
- Deletes tmp file (unless `--keep`)

## Important

- Do NOT use WebFetch for YouTube URLs
- Language codes can be chained: `--lang=en,ru`
