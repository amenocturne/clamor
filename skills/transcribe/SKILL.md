---
name: transcribe
description: Audio transcription. Use when user has audio/video files that need transcription. Produces text transcripts using Whisper locally or via API.
author: amenocturne
---

# Audio Transcription

Transcribe audio files when no subtitles are available.

> All script paths below are relative to this skill folder.

## When to Use

- Audio file needs transcription (podcast, voice memo, recording, etc.)

## Requirements

- **Local**: `faster-whisper` (auto-installed by uv)
- **API**: `OPENROUTER_API_KEY` environment variable
- **Large files**: `ffmpeg` for chunking

## Scripts

### Local (offline, private)

```bash
uv run scripts/transcribe.py <audio_file> [--model=MODEL] [--lang=LANG] [--output=PATH]
```

- Uses faster-whisper (local Whisper)
- Best quality: `--model=large-v3` (~10GB VRAM)
- Good balance: `--model=medium` (~5GB VRAM)
- Fast/CPU: `--model=small`
- Default output: `tmp/<filename>.txt`

### API (fast, no GPU)

```bash
uv run scripts/transcribe_api.py <audio_file> [--lang=LANG] [--output=PATH]
```

- Uses OpenRouter API with Gemini Flash
- Requires `OPENROUTER_API_KEY` env var
- Auto-chunks files over 18MB
- Default output: `tmp/<filename>.txt`

## Workflow

1. Download audio (if from YouTube):
   ```bash
   yt-dlp -x --audio-format mp3 -o "tmp/%(id)s.%(ext)s" <url>
   ```

2. Transcribe:
   ```bash
   uv run scripts/transcribe.py tmp/audio.mp3
   # or
   uv run scripts/transcribe_api.py tmp/audio.mp3
   ```

3. Output saved to `tmp/<filename>.txt`

## Options

Both scripts support:
- `--output=PATH`: Custom output file path
- `--lang=LANG`: Language hint (e.g., `ru`, `en`)
- `--timestamps`: Include timestamps in output
