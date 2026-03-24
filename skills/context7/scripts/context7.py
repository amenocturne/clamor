# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///

"""Context7 CLI — fetch up-to-date library documentation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx

BASE_URL = "https://context7.com/api"
DEFAULT_TOKENS = 10000


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    api_key = os.environ.get("CONTEXT7_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _get(path: str, params: dict[str, Any]) -> httpx.Response:
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{BASE_URL}{path}", params=params, headers=_headers())
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After", "?")
            print(f"Rate limited. Retry after {retry}s.", file=sys.stderr)
            sys.exit(1)
        if resp.status_code >= 400:
            try:
                err = resp.json()
                msg = err.get("message", err.get("error", resp.text))
            except Exception:
                msg = resp.text
            print(f"Error {resp.status_code}: {msg}", file=sys.stderr)
            sys.exit(1)
        return resp


def search(library_name: str, query: str = "") -> list[dict]:
    resp = _get("/v2/libs/search", {
        "libraryName": library_name,
        "query": query or library_name,
    })
    data = resp.json()
    return data.get("results", [])


def format_search_results(results: list[dict]) -> str:
    if not results:
        return "No libraries found."
    lines = []
    for r in results[:10]:
        snippets = r.get("totalSnippets", 0)
        score = r.get("benchmarkScore")
        score_str = f"  score={score:.0f}" if score else ""
        versions = r.get("versions", [])
        ver_str = f"  versions=[{', '.join(versions[:5])}]" if versions else ""
        lines.append(f"  {r['id']}  —  {r.get('title', '?')}  ({snippets} snippets{score_str}{ver_str})")
    return "Libraries found:\n" + "\n".join(lines)


def fetch_docs(library_id: str, query: str, max_tokens: int = DEFAULT_TOKENS) -> str:
    resp = _get("/v2/context", {
        "libraryId": library_id,
        "query": query,
        "type": "txt",
        "tokens": max_tokens,
    })
    return resp.text


def resolve_and_fetch(library_name: str, query: str, max_tokens: int = DEFAULT_TOKENS) -> str:
    results = search(library_name, query)
    if not results:
        return f"No library found for '{library_name}'. Try alternative names."

    best = results[0]
    library_id = best["id"]
    title = best.get("title", library_id)

    docs = fetch_docs(library_id, query, max_tokens)
    header = f"# {title} ({library_id})\n\n"
    return header + docs


def cmd_search(args: argparse.Namespace) -> None:
    results = search(args.library)
    print(format_search_results(results))


def cmd_docs(args: argparse.Namespace) -> None:
    if args.id:
        output = fetch_docs(args.id, args.query, args.tokens)
    else:
        if not args.library:
            print("Error: library name required (or use --id)", file=sys.stderr)
            sys.exit(1)
        output = resolve_and_fetch(args.library, args.query, args.tokens)
    print(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Context7 — library documentation")
    sub = parser.add_subparsers(dest="command", required=True)

    p_search = sub.add_parser("search", help="Search for libraries")
    p_search.add_argument("library", help="Library name to search")
    p_search.set_defaults(func=cmd_search)

    p_docs = sub.add_parser("docs", help="Fetch documentation")
    p_docs.add_argument("library", nargs="?", help="Library name")
    p_docs.add_argument("query", help="What to look up")
    p_docs.add_argument("--id", help="Exact library ID (skip resolve)")
    p_docs.add_argument("--tokens", type=int, default=DEFAULT_TOKENS, help="Max token budget")
    p_docs.set_defaults(func=cmd_docs)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
