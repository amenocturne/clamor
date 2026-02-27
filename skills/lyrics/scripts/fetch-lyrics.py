# /// script
# requires-python = ">=3.11"
# dependencies = ["lyricsgenius"]
# ///
"""Fetch song lyrics from Genius API."""

import argparse
import json
import os
import sys
from pathlib import Path

import lyricsgenius


def get_token() -> str:
    """Get Genius API token from config or environment."""
    # Try environment variable first
    token = os.environ.get("GENIUS_ACCESS_TOKEN")
    if token:
        return token

    # Try agentic-kit.json config
    config_paths = [
        Path.home() / "Vault/Projects/.claude/agentic-kit.json",
        Path.home() / ".claude/agentic-kit.json",
    ]

    for config_path in config_paths:
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
                if "genius_token" in config:
                    return config["genius_token"]
            except (json.JSONDecodeError, KeyError):
                continue

    print("Error: No Genius API token found.", file=sys.stderr)
    print(
        "Set GENIUS_ACCESS_TOKEN or add 'genius_token' to agentic-kit.json",
        file=sys.stderr,
    )
    sys.exit(1)


def create_genius_client(token: str) -> lyricsgenius.Genius:
    """Create configured Genius client."""
    genius = lyricsgenius.Genius(token)
    genius.remove_section_headers = False  # Keep [Chorus], [Verse] etc.
    genius.verbose = False
    genius.skip_non_songs = True
    return genius


def fetch_song(genius: lyricsgenius.Genius, artist: str, song: str) -> str | None:
    """Fetch lyrics for a single song."""
    result = genius.search_song(song, artist)
    if result:
        return result.lyrics
    return None


def fetch_artist_songs(
    genius: lyricsgenius.Genius, artist: str, max_songs: int = 10
) -> list[tuple[str, str]]:
    """Fetch multiple songs from an artist. Returns list of (title, lyrics)."""
    artist_obj = genius.search_artist(artist, max_songs=max_songs, sort="popularity")
    if not artist_obj:
        return []

    songs = []
    for song in artist_obj.songs:
        if song.lyrics:
            songs.append((song.title, song.lyrics))
    return songs


def list_artist_songs(
    genius: lyricsgenius.Genius, artist: str, max_songs: int = 50
) -> list[str]:
    """List song titles for an artist without fetching lyrics."""
    artist_obj = genius.search_artist(
        artist, max_songs=max_songs, sort="popularity", get_full_info=False
    )
    if not artist_obj:
        return []
    return [song.title for song in artist_obj.songs]


def format_multiple_songs(artist: str, songs: list[tuple[str, str]]) -> str:
    """Format multiple songs as markdown."""
    lines = [f"# {artist}", ""]
    for title, lyrics in songs:
        lines.append(f"## {title}")
        lines.append("")
        lines.append(lyrics)
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Fetch song lyrics from Genius")
    parser.add_argument("--artist", "-a", required=True, help="Artist name")
    parser.add_argument("--song", "-s", help="Single song title")
    parser.add_argument("--songs", nargs="+", help="Multiple song titles")
    parser.add_argument(
        "--list", action="store_true", help="List artist songs without lyrics"
    )
    parser.add_argument(
        "--all", action="store_true", help="Fetch all songs from artist"
    )
    parser.add_argument(
        "--max", type=int, default=10, help="Max songs to fetch (default: 10)"
    )
    parser.add_argument("--output", "-o", help="Output file path")

    args = parser.parse_args()

    token = get_token()
    genius = create_genius_client(token)

    output = ""

    if args.list:
        songs = list_artist_songs(genius, args.artist, args.max)
        if songs:
            output = "\n".join(f"- {title}" for title in songs)
        else:
            print(f"No songs found for artist: {args.artist}", file=sys.stderr)
            sys.exit(1)

    elif args.song:
        lyrics = fetch_song(genius, args.artist, args.song)
        if lyrics:
            output = lyrics
        else:
            print(f"Song not found: {args.song} by {args.artist}", file=sys.stderr)
            sys.exit(1)

    elif args.songs:
        found_songs = []
        for song_title in args.songs:
            lyrics = fetch_song(genius, args.artist, song_title)
            if lyrics:
                found_songs.append((song_title, lyrics))
            else:
                print(f"Warning: Song not found: {song_title}", file=sys.stderr)
        if found_songs:
            output = format_multiple_songs(args.artist, found_songs)
        else:
            print("No songs found", file=sys.stderr)
            sys.exit(1)

    elif args.all:
        songs = fetch_artist_songs(genius, args.artist, args.max)
        if songs:
            output = format_multiple_songs(args.artist, songs)
        else:
            print(f"No songs found for artist: {args.artist}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output)
        print(f"Saved to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
