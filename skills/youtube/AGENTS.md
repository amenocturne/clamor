# YouTube Transcript Fetcher

Fetch transcripts from YouTube videos.

## Usage

When user provides a YouTube URL:

1. Download transcript to tmp:
   ```bash
   uv run scripts/yt-subs.py <url>
   ```
   Saves to `tmp/<video_id>.txt`

2. Create source note with `{{transcript}}` placeholder (don't paste content)

3. Inject transcript into source note:
   ```bash
   uv run scripts/inject-transcript.py sources/youtube/<note-name>.md
   ```

## Scripts

### yt-subs.py

```
yt-subs.py <url> [--output PATH] [--lang LANG] [--raw]
```

- `--output`: Save to file instead of stdout (default: stdout, or tmp/<id>.txt)
- `--lang`: Preferred language codes, comma-separated (default: en)
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

If no captions exist, inform the user. Audio transcription requires a separate tool like Whisper.

## Important

- Do NOT use WebFetch for YouTube URLs
- Do NOT paste transcripts manually — use inject-transcript.py
- Language codes can be chained: `--lang=en,ru`
