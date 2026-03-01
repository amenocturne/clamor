---
name: youtube
description: YouTube transcript fetcher. Use when user shares a YouTube URL and wants to process or summarize the content. Produces transcript text without needing to watch the video.
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

## Handling Long Transcripts

If the transcript is too long to fit in context or would consume too much of it:

1. **Spawn a subagent** (Task tool with `subagent_type=general-purpose`) to read the full transcript
2. The subagent should produce a **section summary** with:
   - Brief description of what's discussed in each section
   - Line numbers or character offsets for each section
3. Use this summary to navigate directly to relevant sections when needed

Example subagent prompt:
```
Read the transcript at tmp/<video_id>.txt and create a section-by-section summary.
For each logical section, provide:
- Line range (e.g., lines 1-50)
- Brief description of topics discussed
Return the summary so I can navigate directly to relevant parts.
```

## Important

- Do NOT use WebFetch for YouTube URLs
- Language codes can be chained: `--lang=en,ru`
