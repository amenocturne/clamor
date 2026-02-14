---
name: youtube
description: Fetch YouTube transcripts for processing
author: amenocturne
---

# YouTube Transcript Fetcher

Fetch transcripts from YouTube videos.

> All script paths below are relative to this skill folder.

## Usage

When user provides a YouTube URL:

1. Download transcript:
   ```bash
   uv run scripts/yt-subs.py <url> --output=tmp/<video_id>.txt
   ```
   The `tmp/` folder is relative to the project root.

2. Create source note with `{{transcript}}` placeholder (don't paste content)

3. Inject transcript into source note:
   ```bash
   uv run scripts/inject-transcript.py sources/youtube/<note-name>.md
   ```

## Scripts

### yt-subs.py

```
yt-subs.py <url> [--output=PATH] [--lang=LANG] [--raw]
```

- `--output`: Save to file (default: stdout)
- `--lang`: Preferred language codes, comma-separated (default: en,ru)
- `--raw`: Output raw VTT format instead of cleaned text

### inject-transcript.py

```
inject-transcript.py <source-note> [--keep]
```

- Reads source URL from note's frontmatter
- Finds transcript in `tmp/<video_id>.txt`
- Replaces `{{transcript}}` placeholder with formatted content
- Deletes tmp file (unless `--keep`)

## No Subtitles Available?

If no captions exist, use the **transcribe** skill to transcribe from audio instead.

## Important

- Do NOT use WebFetch for YouTube URLs
- Do NOT paste transcripts manually — use inject-transcript.py
- Language codes can be chained: `--lang=en,ru`
