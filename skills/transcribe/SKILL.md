---
name: transcribe
description: Transcribe audio files using Whisper (local) or API
author: amenocturne
---

# Audio Transcription

Transcribe audio files using local Whisper model or OpenRouter API.

## Features

- Local transcription with faster-whisper (offline, private)
- API transcription with Gemini Flash (fast, no GPU needed)
- Auto-chunking for large files
- Multiple language support

## Requirements

- **Local**: `faster-whisper` (auto-installed by uv)
- **API**: `OPENROUTER_API_KEY` environment variable
- **Large files**: `ffmpeg` for chunking
