---
name: lyrics
description: Song lyrics fetcher from Genius. Use when user wants to get lyrics for songs, artists, or albums. Produces clean lyrics text for notes or analysis.
author: amenocturne
---

# Lyrics Fetcher

Fetch song lyrics from Genius using the lyricsgenius library.

> All script paths below are relative to this skill folder.

## Configuration

The script reads the Genius API token from `~/.claude/projects/.claude/agentic-kit.json` under the `genius_token` key. Alternatively, set `GENIUS_ACCESS_TOKEN` environment variable.

## Usage

### Fetch a single song

```bash
uv run scripts/fetch-lyrics.py --artist "Artist Name" --song "Song Title"
```

### List all songs by an artist

```bash
uv run scripts/fetch-lyrics.py --artist "Artist Name" --list
```

### Fetch multiple songs by an artist

```bash
uv run scripts/fetch-lyrics.py --artist "Artist Name" --songs "Song 1" "Song 2" "Song 3"
```

### Fetch all songs from an artist (up to N)

```bash
uv run scripts/fetch-lyrics.py --artist "Artist Name" --all --max 20
```

### Save to file

```bash
uv run scripts/fetch-lyrics.py --artist "Artist Name" --song "Song Title" --output tmp/lyrics.txt
```

## Output Format

For single songs, outputs plain lyrics text.

For multiple songs (--songs, --all), outputs markdown format:

```markdown
# Artist Name

## Song Title 1

[Verse 1]
Lyrics here...

## Song Title 2

[Chorus]
More lyrics...
```

## Creating Source Notes

When creating source notes for albums/artists in the knowledge base:

1. Create a directory: `sources/music/<artist-slug>/`
2. Create individual song notes or a combined album note
3. Use the lyrics output as content

## Important

- Genius may not have all songs, especially for obscure artists
- Russian and other non-Latin artists work well
- Section headers like [Verse], [Chorus] are preserved by default
