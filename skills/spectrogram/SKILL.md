---
name: spectrogram
description: Audio spectrogram generator. Use when the user asks you to listen to, analyze, or compare audio — sound design, mixing, mastering, genre identification. Generates spectrogram + waveform images optimized for LLM visual analysis.
author: amenocturne
---

# Spectrogram Generator

Generate spectrogram images from audio files so Claude can visually analyze how music sounds.

> Run commands via justfile: `just -f <skill-path>/justfile <recipe> [flags]`

## Recipes

### generate

Generate spectrogram + waveform images from an audio file.

```bash
just -f <skill-path>/justfile generate <audio-file> [--output=PATH] [--stereo] [--start=N] [--end=N] [--chunk=N] [--no-chunk] [--px-per-sec=N] [--fmin=N] [--fmax=N] [--top-db=N]
```

- `--output`: Output directory for PNGs (default: prints to stdout)
- `--stereo`: Generate stereo L/R spectrograms (default: mono)
- `--start`: Start time in seconds (default: 0)
- `--end`: End time in seconds (default: full track)
- `--chunk`: Chunk duration in seconds (default: 60)
- `--no-chunk`: Force single image for full track
- `--px-per-sec`: Time resolution in pixels per second (default: 25)
- `--fmin`: Min frequency in Hz (default: 20). Use to zoom into frequency ranges.
- `--fmax`: Max frequency in Hz (default: 16000). Use to zoom into frequency ranges.
- `--top-db`: Dynamic range from peak in dB (default: 80). Lower values reveal louder features, higher values show quieter detail.

**All paths must be absolute.** `just` runs from the justfile's directory, so relative paths resolve there, not in the project root.

## Output

Produces one or more PNG images. Each image contains:

- Mel spectrogram (log frequency scale, 20Hz–16kHz) — ~85% of image
- Waveform amplitude strip — ~15% of image
- Time axis labels showing absolute position in track

For tracks > 60s, auto-chunks into separate images with ~0.5s overlap.

Script prints generated file paths to stdout (one per line) — read these to view the spectrograms.

## Reading Spectrograms

When analyzing generated spectrograms, look for:

- **Horizontal bands**: sustained tones, harmonics (timbre signature)
- **Vertical lines**: transients (drums, plucks, attacks)
- **Frequency distribution**: where energy concentrates (genre fingerprint)
- **Gaps/breaks**: arrangement structure, drops, transitions
- **Harmonic spacing**: evenly spaced = clean tone, dense/irregular = distortion/noise
- **Waveform shape**: dynamics, compression level, loudness

## Example Workflow

```bash
# Full track analysis (auto-chunks at 60s)
just -f <skill-path>/justfile generate /path/to/track.mp3 --output=/project-root/tmp/
# Then read the generated images to analyze
```

## Zooming In

Use these flags to get a closer look at specific regions:

```bash
# Time zoom — focus on the drop at 0:30-0:50
just -f <skill-path>/justfile generate track.mp3 --start=30 --end=50 --no-chunk --output=/project-root/tmp/

# Frequency zoom — inspect bass content only (20-500Hz)
just -f <skill-path>/justfile generate track.mp3 --fmin=20 --fmax=500 --output=/project-root/tmp/

# Frequency zoom — inspect mid/high detail (1kHz-16kHz)
just -f <skill-path>/justfile generate track.mp3 --fmin=1000 --fmax=16000 --output=/project-root/tmp/

# Dynamic range — reveal quiet details (wider range)
just -f <skill-path>/justfile generate track.mp3 --top-db=120 --output=/project-root/tmp/

# Dynamic range — focus on loud features only
just -f <skill-path>/justfile generate track.mp3 --top-db=40 --output=/project-root/tmp/

# Combined — zoom into bass at the drop with high time resolution
just -f <skill-path>/justfile generate track.mp3 --start=30 --end=50 --fmin=20 --fmax=500 --px-per-sec=50 --no-chunk --output=/project-root/tmp/
```

**When to zoom:**

- Saw something interesting in the overview → time zoom with `--start`/`--end`
- Need to distinguish bass instruments → frequency zoom with low `--fmax`
- Spectrogram looks too dark/bright → adjust `--top-db`
- Need to see fine rhythmic detail → increase `--px-per-sec`
