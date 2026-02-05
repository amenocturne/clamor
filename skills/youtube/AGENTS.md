# YouTube Transcript Fetcher

Fetch transcripts from YouTube videos.

## Usage

When user provides a YouTube URL:

1. Run the transcript script:
   ```bash
   uv run scripts/yt-subs.py <url>
   ```

2. Script outputs transcript to stdout or saves to specified path

3. Use the transcript as needed (summarize, extract concepts, etc.)

## Script Options

```
yt-subs.py <url> [--output PATH] [--lang LANG] [--raw]
```

- `--output`: Save to file instead of stdout (default: stdout)
- `--lang`: Preferred language codes, comma-separated (default: en)
- `--raw`: Output raw VTT format instead of cleaned text

## No Subtitles Available?

If no captions exist, inform the user. Audio transcription is a separate concern — the user would need a transcription tool like Whisper.

## Important

- Do NOT use WebFetch for YouTube URLs — always use this script
- The script handles both auto-generated and manual captions
- Language codes can be chained: `--lang=en,ru` tries English first, then Russian
