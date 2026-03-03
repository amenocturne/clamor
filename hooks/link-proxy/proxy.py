#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
r"""
Link Proxy — Local HTTP proxy for Anthropic Messages API traffic.

Sits between Claude Code and a corporate LLM proxy. Intercepts API requests
to replace internal URLs with deterministic placeholders (so the corporate
proxy sees nothing to mask), then restores placeholders back to URLs in
responses before Claude Code reads them.

    Request flow:
    Claude Code -> Link Proxy (URLs -> placeholders) -> Corp Proxy -> Anthropic API

    Response flow:
    Claude Code <- Link Proxy (placeholders -> URLs) <- Corp Proxy <- Anthropic API


ARCHITECTURE OVERVIEW
=====================

The proxy is a single-threaded-per-request HTTP server using stdlib only.
It listens on localhost, accepts HTTP requests intended for the Anthropic
Messages API, transforms them, forwards to upstream (optionally through
a corporate HTTPS proxy), and streams/buffers the response back.

Reuses URL pattern matching and placeholder logic from main.py:
  - build_url_pattern(domains) -> compiled regex
  - url_to_placeholder(url) -> (placeholder_string, hash)
  - transform_text(text, pattern) -> (transformed, new_mappings)
  - restore_text(text, mappings) -> restored_text
  - PLACEHOLDER_RE -> regex matching [InternalLink_<prefix>_<hash>]

These are imported directly from main.py (same directory).


SHARED STATE
============

url_mappings: dict[str, str]
    Maps hash -> original_url. Append-only. Populated during request
    transformation, consumed during response restoration.
    Protected by threading.Lock since ThreadingHTTPServer handles
    requests concurrently.

url_pattern: re.Pattern | None
    Compiled regex for matching internal URLs. Built once at startup
    from domains.txt. Immutable after init, no lock needed.


CONFIGURATION
=============

Resolved at startup in this priority order (env var / CLI arg / default):

    LINK_PROXY_PORT     / --port      / 18923
        Port to listen on.

    ANTHROPIC_API_URL   (env only)    / https://api.anthropic.com
        Upstream API base URL. This is what the proxy forwards to.

    HTTPS_PROXY         (env only)    / None
        Corporate proxy URL. If set, the proxy tunnels HTTPS through it
        via HTTP CONNECT. IMPORTANT: must be captured at startup BEFORE
        we override HTTPS_PROXY to prevent Claude Code from double-proxying.

    LINK_PROXY_DEBUG    (env only)    / 0
        Set to "1" for verbose debug logging to stderr.

    domains.txt         (file)
        Same file used by the hook. One domain per line, # for comments.
        Read once at startup.


STARTUP FLOW
============

    1. Parse CLI args (--port)
    2. Capture HTTPS_PROXY from environment (save it, then unset it so
       child processes like Claude Code don't use it directly)
    3. Read ANTHROPIC_API_URL from environment
    4. Load domains.txt, compile URL pattern
    5. Load existing mappings from data/mappings.json (seed from prior sessions)
    6. Print config summary to stderr:
       - Listening port
       - Upstream URL
       - Corporate proxy (if any)
       - Number of domains configured
       - Number of pre-loaded mappings
    7. Print suggested usage:
       export ANTHROPIC_BASE_URL=http://localhost:<port>
    8. Start ThreadingHTTPServer, serve_forever()


REQUEST HANDLING
================

All requests are handled by ProxyHandler(BaseHTTPRequestHandler).
Only POST to /v1/messages is intercepted for transformation.
All other paths are forwarded as-is (passthrough).

For /v1/messages POST:

    1. Read Content-Length, buffer entire request body
    2. Parse JSON
    3. Detect streaming: body.get("stream", False)
    4. Walk the request body and replace URLs in all string values:
       - messages[].content  (string or array of content blocks)
       - system  (string or array of content blocks)
       - tools[].description
       - Deep-walk tool_use input (arbitrary nested JSON)
       - Deep-walk tool_result content (string or array of blocks)
    5. Save any new mappings (hash -> url) to shared state
    6. Re-serialize JSON, forward to upstream
    7. Handle response based on streaming mode


RESPONSE HANDLING
=================

Non-streaming (stream=false or absent):
    1. Buffer full response body from upstream
    2. Parse JSON
    3. Deep-walk all string values, restore placeholders -> URLs
    4. Re-serialize, send to client with correct Content-Length

Streaming (stream=true):
    1. Set response headers, begin chunked transfer or raw streaming
    2. Read SSE events from upstream line by line
    3. For each SSE event:
       a. Parse "event: <type>" and "data: <json>"
       b. Route by event type (see SSE Event Routing below)
       c. Serialize modified event, forward to client immediately
    4. On stream end, flush any buffered content


SSE EVENT ROUTING
=================

Events that need placeholder restoration:

    content_block_start
        - type "text": no URLs expected yet, pass through
        - type "tool_use": no URLs, pass through
        - type "web_search_tool_result": may contain URLs in
          search_result.url / search_result.title — restore them
        - type "thinking": pass through (no URLs in initial block)

    content_block_delta
        - text_delta: accumulate text, buffer partial placeholders,
          emit restored text (see Streaming Buffer Algorithm)
        - input_json_delta: accumulate partial JSON string per block,
          do NOT emit until content_block_stop
        - thinking_delta: accumulate and buffer like text_delta
        - citations_delta: may contain URLs, restore inline

    content_block_stop
        - For text/thinking blocks: flush remaining buffer
        - For tool_use blocks: parse accumulated JSON, deep-walk and
          restore all placeholders, emit corrected input_json_delta
          events (or a single synthetic one)

    message_start, message_delta, message_stop, ping:
        Pass through unmodified.

Events/fields to NEVER modify:
    - encrypted_content, encrypted_index, signature (web search)
    - redacted_thinking.data
    - Base64-encoded image/document source.data
    - Any non-string JSON values


STREAMING BUFFER ALGORITHM (text_delta)
=======================================

The core challenge: a placeholder like [InternalLink_wiki_3e5f8279] might
be split across multiple SSE text_delta events. We must detect partial
placeholders at chunk boundaries and delay emission until we can determine
if it completes.

State per content block (indexed by block index):
    buffer: str  — accumulated text not yet emitted

Algorithm (pseudocode):

    def handle_text_delta(block_index, new_text):
        buf = block_buffers[block_index]
        buf.text += new_text

        # Try to restore complete placeholders in buffer
        restored = restore_text(buf.text, url_mappings)

        # Check if buffer ends with a potential partial placeholder.
        # A partial is: "[" followed by characters matching the start
        # of "InternalLink_<prefix>_<hash>]" but not yet closed with "]"
        partial_match = PARTIAL_PLACEHOLDER_RE.search(restored)

        if partial_match:
            # Split: emit everything before the partial, keep partial buffered
            emit_text = restored[:partial_match.start()]
            buf.text = restored[partial_match.start():]
        else:
            # No partial detected, emit everything
            emit_text = restored
            buf.text = ""

        if emit_text:
            send_text_delta_event(block_index, emit_text)

    def handle_block_stop(block_index):
        buf = block_buffers[block_index]
        if buf.text:
            # No more data coming — emit whatever remains as-is
            # (incomplete placeholder patterns are just literal text)
            send_text_delta_event(block_index, buf.text)
        del block_buffers[block_index]

PARTIAL_PLACEHOLDER_RE pattern:
    \[(?:I(?:n(?:t(?:e(?:r(?:n(?:a(?:l(?:L(?:i(?:n(?:k(?:_[a-zA-Z0-9]*(?:_[a-f0-9]{0,7})?)?)?)?)?)?)?)?)?)?)?)?)?)?$

    This matches any trailing suffix that could be the beginning of
    "[InternalLink_<prefix>_<hash>]". The progressive optional groups
    ensure we catch even just a trailing "[" or "[I" or "[Intern..." etc.

    Simpler alternative (less precise, more conservative):
    \[[A-Za-z0-9_]{0,50}$

    The simpler version buffers more aggressively (any trailing "[..."
    without a closing "]") but is easier to reason about. Use this one
    unless benchmarking shows unacceptable latency from over-buffering.


STREAMING BUFFER ALGORITHM (input_json_delta)
=============================================

tool_use blocks emit input as a series of input_json_delta events, each
containing a partial JSON string fragment. These fragments concatenated
form valid JSON (the tool's input object).

Strategy: accumulate all fragments, do NOT forward them to the client.
At content_block_stop, parse the full JSON, deep-walk to restore
placeholders, re-serialize, and emit as a single input_json_delta event
followed by content_block_stop.

This adds latency (client sees tool input only after the full block),
but tool_use input is typically small and Claude Code doesn't render it
progressively anyway.

    State per tool_use block:
        json_fragments: list[str]

    def handle_input_json_delta(block_index, partial_json):
        block_buffers[block_index].json_fragments.append(partial_json)
        # Do NOT emit anything

    def handle_tool_use_block_stop(block_index):
        full_json_str = "".join(block_buffers[block_index].json_fragments)
        parsed = json.loads(full_json_str)
        restored = deep_walk_restore(parsed, url_mappings)
        restored_str = json.dumps(restored)
        send_input_json_delta_event(block_index, restored_str)
        send_block_stop_event(block_index)
        del block_buffers[block_index]


REQUEST BODY TRANSFORMATION — FIELD WALKTHROUGH
================================================

The Anthropic Messages API request body has these URL-relevant fields:

    body["system"]
        String or list of content blocks.
        If string: transform_text(system, pattern)
        If list: walk each block (see content block walking)

    body["messages"]
        List of message objects. Each has:
        - role: "user" or "assistant"
        - content: string or list of content blocks

        If content is string: transform_text(content, pattern)
        If content is list: walk each block

    body["tools"]
        List of tool definitions. Each has:
        - description: string — transform_text()
        - input_schema: JSON schema — skip (no user URLs in schemas)

Content block types and their URL-relevant fields:

    {"type": "text", "text": "..."}
        Transform text field.

    {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
        Deep-walk input (arbitrary nested JSON).
        input can contain any structure — recursively walk all
        string values, transform each.

    {"type": "tool_result", "tool_use_id": "...", "content": ...}
        content is string or list of content blocks.
        If string: transform.
        If list: walk each block (can contain text, image blocks).

    {"type": "image", "source": {"type": "base64", "data": "..."}}
        SKIP — binary data, no URLs to transform.

    {"type": "document", "source": {"type": "base64", "data": "..."}}
        SKIP — binary data.

    {"type": "thinking", "thinking": "..."}
        Transform thinking field.
        SKIP "signature" field.

    {"type": "redacted_thinking", "data": "..."}
        SKIP entirely — encrypted, cannot parse.

    {"type": "server_tool_use" / "web_search_tool_result" / ...}
        These appear in responses, not requests. Unlikely in request
        messages but if present, deep-walk string fields except
        encrypted_content/encrypted_index/signature.


DEEP WALK FUNCTIONS
===================

Two variants needed:

    deep_walk_transform(obj, pattern) -> (transformed_obj, new_mappings)
        Recursively walks arbitrary JSON (dicts, lists, strings).
        Applies transform_text to every string value.
        Returns transformed copy and merged mappings dict.

    deep_walk_restore(obj, mappings) -> restored_obj
        Recursively walks arbitrary JSON.
        Applies restore_text to every string value.
        Returns restored copy.

Both skip known binary/encrypted fields (see skip list).


UPSTREAM CONNECTION
===================

    connect_upstream() -> http.client.HTTPSConnection

    If HTTPS_PROXY is configured:
        1. Parse proxy URL to get proxy_host, proxy_port
        2. Create HTTPSConnection to proxy_host:proxy_port
        3. Call set_tunnel(upstream_host, upstream_port) for CONNECT
        4. Connection will tunnel HTTPS through the corporate proxy

    If no HTTPS_PROXY:
        1. Create HTTPSConnection directly to upstream_host:upstream_port

    Timeouts:
        Connect timeout: 30 seconds
        Read timeout for non-streaming: 120 seconds
        Read timeout for streaming: 300 seconds (or None — rely on
        upstream to close the connection)


ERROR HANDLING
==============

    Upstream connection refused / DNS failure:
        -> 502 Bad Gateway
        -> Body: {"type": "error", "error": {"type": "api_error",
           "message": "Link proxy: could not connect to upstream"}}

    Upstream timeout (connect):
        -> 504 Gateway Timeout
        -> Body: {"type": "error", "error": {"type": "timeout_error",
           "message": "Link proxy: upstream connection timed out"}}

    Upstream timeout (read, non-streaming):
        -> 504 Gateway Timeout

    Upstream returns 4xx/5xx:
        -> Forward status code and body as-is (after placeholder
           restoration in case the error message contains any)

    Request body not valid JSON:
        -> 400 Bad Request
        -> Body: {"type": "error", "error": {"type": "invalid_request_error",
           "message": "Link proxy: request body is not valid JSON"}}

    Internal proxy error (bug in transformation):
        -> 500 Internal Server Error
        -> Log full traceback to stderr
        -> Body: {"type": "error", "error": {"type": "api_error",
           "message": "Link proxy: internal error during transformation"}}


FUNCTION SIGNATURES
===================

# --- Configuration ---

def parse_args() -> argparse.Namespace:
    '''Parse --port CLI argument.'''

def load_config() -> Config:
    '''Load all configuration from env vars, CLI args, and files.
    Returns a Config namedtuple/dataclass with: port, upstream_url,
    upstream_host, upstream_port, corp_proxy_url, corp_proxy_host,
    corp_proxy_port, url_pattern, debug.'''

def print_config(config: Config) -> None:
    '''Print configuration summary to stderr.'''


# --- Shared state ---

class ProxyState:
    '''Thread-safe shared state for the proxy.
    Fields: url_mappings (dict), lock (threading.Lock), config (Config).'''


# --- URL transformation (imported from main.py) ---

# load_domains() -> list[str]
# build_url_pattern(domains) -> re.Pattern | None
# url_to_placeholder(url) -> tuple[str, str]
# transform_text(text, pattern) -> tuple[str, dict[str, str]]
# restore_text(text, mappings) -> str
# PLACEHOLDER_RE


# --- Deep walk ---

def deep_walk_transform(obj: Any, pattern: re.Pattern, skip_keys: set[str]) -> tuple[Any, dict]:
    '''Recursively transform all string values in nested JSON structure.
    Skips keys in skip_keys set. Returns (transformed_obj, new_mappings).'''

def deep_walk_restore(obj: Any, mappings: dict[str, str], skip_keys: set[str]) -> Any:
    '''Recursively restore placeholders in all string values.
    Skips keys in skip_keys set. Returns restored copy.'''

SKIP_KEYS: set[str] = {"encrypted_content", "encrypted_index", "signature", "data"}
# Note: "data" is skipped because it holds base64 image/document content
# and redacted_thinking data. URL strings never appear in these fields.
# HOWEVER: "data" in SSE "data: ..." lines is NOT a JSON key — it's the
# SSE framing. The skip applies only to JSON object keys during deep walk.


# --- Request transformation ---

def transform_request_body(body: dict, pattern: re.Pattern) -> tuple[dict, dict]:
    '''Transform an Anthropic Messages API request body.
    Walks system, messages, and tools fields.
    Returns (transformed_body, new_mappings).'''

def transform_messages(messages: list[dict], pattern: re.Pattern) -> tuple[list, dict]:
    '''Transform messages array. Returns (transformed, mappings).'''

def transform_content(content: str | list, pattern: re.Pattern) -> tuple[str | list, dict]:
    '''Transform a content field (string or list of blocks).'''

def transform_content_block(block: dict, pattern: re.Pattern) -> tuple[dict, dict]:
    '''Transform a single content block based on its type.'''


# --- Response transformation (non-streaming) ---

def restore_response_body(body: dict, mappings: dict[str, str]) -> dict:
    '''Restore placeholders in a non-streaming response body.
    Walks content blocks in the response.'''


# --- Response transformation (streaming) ---

class StreamBuffer:
    '''Per-content-block buffer state for streaming restoration.
    Fields: block_type (str), text_buffer (str), json_fragments (list[str]).'''

def handle_sse_event(
    event_type: str,
    data: dict,
    block_buffers: dict[int, StreamBuffer],
    mappings: dict[str, str],
) -> list[tuple[str, dict]]:
    '''Process one SSE event. Returns list of (event_type, data) tuples
    to emit (may be 0, 1, or multiple events).'''

def flush_text_buffer(
    block_index: int,
    new_text: str,
    block_buffers: dict[int, StreamBuffer],
    mappings: dict[str, str],
) -> str:
    '''Append new_text to block buffer, restore complete placeholders,
    return text safe to emit (excluding any trailing partial placeholder).'''

def flush_block_stop(
    block_index: int,
    block_buffers: dict[int, StreamBuffer],
    mappings: dict[str, str],
) -> list[tuple[str, dict]]:
    '''Flush remaining buffer for a block that just ended.
    For text blocks: emit remaining text_delta + block_stop.
    For tool_use blocks: parse accumulated JSON, restore, emit
    input_json_delta + block_stop.'''

PARTIAL_PLACEHOLDER_RE: re.Pattern
# Matches trailing text that could be the start of a placeholder.
# Pattern: \[[A-Za-z0-9_]{0,50}$
# Conservative: buffers any "[" followed by up to 50 word chars at end of string.


# --- Upstream connection ---

def connect_upstream(config: Config) -> http.client.HTTPSConnection:
    '''Create connection to upstream, optionally tunneled through corp proxy.'''

def forward_request(
    conn: http.client.HTTPSConnection,
    method: str,
    path: str,
    headers: dict,
    body: bytes,
) -> http.client.HTTPResponse:
    '''Send request to upstream, return response object.'''


# --- HTTP handler ---

class ProxyHandler(BaseHTTPRequestHandler):
    '''HTTP request handler for the proxy.

    Attached to ProxyState via server.proxy_state.

    Methods:
        do_POST() — main handler for /v1/messages
        do_GET()  — passthrough for other endpoints
        do_OPTIONS() — passthrough

        handle_messages_post() — transform request, forward, handle response
        forward_passthrough() — forward request/response without transformation
        stream_response() — handle SSE streaming response with buffering
        send_error_response(status, error_type, message) — Anthropic-format error
        log_debug(msg) — conditional debug logging
    '''


# --- Entry point ---

def main() -> None:
    '''Parse config, initialize state, start server.'''


TRADEOFFS AND CONCERNS
=======================

1. FULL REQUEST BUFFERING
   The entire request body is buffered in memory to parse and transform
   JSON. Anthropic requests can be large (multi-turn conversations with
   images). This is acceptable because: (a) Claude Code already buffers
   the full request, (b) image data is base64 in JSON so it's already
   all in memory, (c) we skip transforming base64 data fields.

2. TOOL_USE INPUT LATENCY
   input_json_delta events are accumulated and not forwarded until
   content_block_stop. This delays the client seeing tool input by the
   duration of the tool_use block generation. Acceptable because Claude
   Code doesn't progressively render tool input, and tool inputs are
   typically small (< 10KB).

3. TEXT_DELTA BUFFERING LATENCY
   When a "[" appears at the end of a text chunk, we buffer up to ~50
   characters waiting to see if it's a placeholder. In the worst case
   (a literal "[" followed by normal text in the next chunk), this adds
   one SSE event of latency (~50-200ms). Negligible for UX.

4. THREAD SAFETY
   url_mappings is append-only with Lock protection. Since we only add
   entries (never delete or modify), the worst case of a race is a
   duplicate insert of the same key with the same value. No data
   corruption possible.

5. MAPPINGS PERSISTENCE
   Mappings are loaded from data/mappings.json at startup and held in
   memory. They are NOT persisted back during proxy operation — the
   proxy is stateless across restarts. The hook's main.py manages
   persistent mappings. The proxy's in-memory mappings grow monotonically
   during a session. If the proxy restarts, previously seen URLs will
   be re-mapped with identical hashes (deterministic), so the same
   placeholders will be generated.

6. SKIP_KEYS "data" IS BROAD
   Skipping all "data" keys means we won't transform URLs inside any
   field named "data" anywhere in the JSON tree. This is correct for
   base64 sources and redacted_thinking, but could miss a hypothetical
   future field named "data" that contains URLs. Acceptable risk —
   the Anthropic API schema is well-known and "data" is consistently
   used for binary/opaque content.

7. CONNECTION REUSE
   Each request creates a new upstream connection. For high-throughput
   scenarios, connection pooling would help. Not needed for single-user
   Claude Code usage (one request at a time, typically).

8. HEALTH CHECK
   Consider adding GET / or GET /health that returns 200 with proxy
   status. Useful for scripts that wait for the proxy to be ready.
   Low priority but easy to add.

9. GRACEFUL SHUTDOWN
   signal.signal(SIGINT, ...) and signal.signal(SIGTERM, ...) to call
   server.shutdown(). Ensures in-flight streaming responses complete
   or are cleanly terminated.

10. NO TLS ON LISTENER
    The proxy listens on plain HTTP (localhost only). Claude Code
    connects to http://localhost:PORT. This is fine — traffic never
    leaves the machine. The upstream connection IS over HTTPS.
"""

from __future__ import annotations

import argparse
import http.client
import io
import json
import logging
import os
import re
import signal
import socket
import ssl
import sys
import threading
import traceback
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Imports from main.py (same directory)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from main import (  # noqa: E402
    build_url_pattern,
    load_domains,
    load_mappings,
    restore_text,
    transform_text,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_PORT = 18923
DEFAULT_UPSTREAM = "https://api.anthropic.com"
CONNECT_TIMEOUT = 30
READ_TIMEOUT_NORMAL = 120
READ_TIMEOUT_STREAMING = 300

SKIP_KEYS: set[str] = {"encrypted_content", "encrypted_index", "signature", "data"}

PARTIAL_PLACEHOLDER_RE = re.compile(r"\[[A-Za-z0-9_]{0,50}$")

logger = logging.getLogger("link-proxy")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class Config:
    __slots__ = (
        "port",
        "upstream_url",
        "upstream_host",
        "upstream_port",
        "upstream_path_prefix",
        "corp_proxy_url",
        "corp_proxy_host",
        "corp_proxy_port",
        "url_pattern",
        "debug",
    )

    def __init__(
        self,
        *,
        port: int,
        upstream_url: str,
        upstream_host: str,
        upstream_port: int,
        upstream_path_prefix: str,
        corp_proxy_url: str | None,
        corp_proxy_host: str | None,
        corp_proxy_port: int | None,
        url_pattern: re.Pattern | None,
        debug: bool,
    ) -> None:
        self.port = port
        self.upstream_url = upstream_url
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.upstream_path_prefix = upstream_path_prefix
        self.corp_proxy_url = corp_proxy_url
        self.corp_proxy_host = corp_proxy_host
        self.corp_proxy_port = corp_proxy_port
        self.url_pattern = url_pattern
        self.debug = debug


def parse_args() -> argparse.Namespace:
    """Parse --port CLI argument."""
    parser = argparse.ArgumentParser(description="Link Proxy for Anthropic API")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    return parser.parse_args()


def load_config() -> Config:
    """Load all configuration from env vars, CLI args, and files."""
    args = parse_args()

    port = int(os.environ.get("LINK_PROXY_PORT", 0)) or (args.port or DEFAULT_PORT)
    debug = os.environ.get("LINK_PROXY_DEBUG", "0") == "1"

    if debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="[link-proxy] %(message)s",
            stream=sys.stderr,
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format="[link-proxy] %(message)s",
            stream=sys.stderr,
        )

    # Capture corporate proxy BEFORE clearing it
    corp_proxy_url = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    corp_proxy_host: str | None = None
    corp_proxy_port: int | None = None
    if corp_proxy_url:
        parsed_proxy = urlparse(corp_proxy_url)
        corp_proxy_host = parsed_proxy.hostname
        corp_proxy_port = parsed_proxy.port or 8080
        # Unset so child processes don't double-proxy
        os.environ.pop("HTTPS_PROXY", None)
        os.environ.pop("https_proxy", None)

    upstream_url = os.environ.get("ANTHROPIC_API_URL", DEFAULT_UPSTREAM).rstrip("/")
    parsed_upstream = urlparse(upstream_url)
    upstream_host = parsed_upstream.hostname or "api.anthropic.com"
    upstream_port = parsed_upstream.port or (443 if parsed_upstream.scheme == "https" else 80)
    upstream_path_prefix = parsed_upstream.path.rstrip("/")

    domains = load_domains()
    url_pattern = build_url_pattern(domains) if domains else None

    return Config(
        port=port,
        upstream_url=upstream_url,
        upstream_host=upstream_host,
        upstream_port=upstream_port,
        upstream_path_prefix=upstream_path_prefix,
        corp_proxy_url=corp_proxy_url,
        corp_proxy_host=corp_proxy_host,
        corp_proxy_port=corp_proxy_port,
        url_pattern=url_pattern,
        debug=debug,
    )


def print_config(config: Config) -> None:
    """Print configuration summary to stderr."""
    domains = load_domains()
    mappings = load_mappings()
    print("[link-proxy] === Link Proxy Configuration ===", file=sys.stderr)
    print(
        f"[link-proxy]   Listen:    http://localhost:{config.port}",
        file=sys.stderr,
    )
    print(f"[link-proxy]   Upstream:  {config.upstream_url}", file=sys.stderr)
    if config.corp_proxy_url:
        print(
            f"[link-proxy]   Corp proxy: {config.corp_proxy_url}",
            file=sys.stderr,
        )
    else:
        print("[link-proxy]   Corp proxy: (none)", file=sys.stderr)
    print(
        f"[link-proxy]   Domains:   {len(domains)} configured",
        file=sys.stderr,
    )
    print(
        f"[link-proxy]   Mappings:  {len(mappings)} pre-loaded",
        file=sys.stderr,
    )
    print(f"[link-proxy]   Debug:     {config.debug}", file=sys.stderr)
    print("[link-proxy] ===", file=sys.stderr)
    print(
        f"[link-proxy] Set: export ANTHROPIC_BASE_URL=http://localhost:{config.port}",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
class ProxyState:
    """Thread-safe shared state for the proxy."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.url_mappings: dict[str, str] = {}
        self.lock = threading.Lock()

    def add_mappings(self, new_mappings: dict[str, str]) -> None:
        if not new_mappings:
            return
        with self.lock:
            self.url_mappings.update(new_mappings)

    def get_mappings(self) -> dict[str, str]:
        with self.lock:
            return dict(self.url_mappings)


# ---------------------------------------------------------------------------
# Deep walk functions
# ---------------------------------------------------------------------------
def deep_walk_transform(
    obj: Any,
    pattern: re.Pattern,
    skip_keys: set[str] = SKIP_KEYS,
) -> tuple[Any, dict[str, str]]:
    """Recursively transform all string values in nested JSON."""
    all_mappings: dict[str, str] = {}

    if isinstance(obj, str):
        transformed, new_map = transform_text(obj, pattern)
        all_mappings.update(new_map)
        return transformed, all_mappings

    if isinstance(obj, list):
        result = []
        for item in obj:
            transformed, new_map = deep_walk_transform(item, pattern, skip_keys)
            all_mappings.update(new_map)
            result.append(transformed)
        return result, all_mappings

    if isinstance(obj, dict):
        result_dict: dict[str, Any] = {}
        for key, value in obj.items():
            if key in skip_keys:
                result_dict[key] = value
            else:
                transformed, new_map = deep_walk_transform(value, pattern, skip_keys)
                all_mappings.update(new_map)
                result_dict[key] = transformed
        return result_dict, all_mappings

    return obj, all_mappings


def deep_walk_restore(
    obj: Any,
    mappings: dict[str, str],
    skip_keys: set[str] = SKIP_KEYS,
) -> Any:
    """Recursively restore placeholders in all string values."""
    if isinstance(obj, str):
        return restore_text(obj, mappings)

    if isinstance(obj, list):
        return [deep_walk_restore(item, mappings, skip_keys) for item in obj]

    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, value in obj.items():
            if key in skip_keys:
                result[key] = value
            else:
                result[key] = deep_walk_restore(value, mappings, skip_keys)
        return result

    return obj


# ---------------------------------------------------------------------------
# Request transformation
# ---------------------------------------------------------------------------
def transform_content_block(block: dict, pattern: re.Pattern) -> tuple[dict, dict[str, str]]:
    """Transform a single content block based on its type."""
    block = dict(block)  # shallow copy
    mappings: dict[str, str] = {}
    block_type = block.get("type", "")

    if block_type == "text":
        text = block.get("text", "")
        if isinstance(text, str):
            transformed, new_map = transform_text(text, pattern)
            mappings.update(new_map)
            block["text"] = transformed

    elif block_type == "thinking":
        thinking = block.get("thinking", "")
        if isinstance(thinking, str):
            transformed, new_map = transform_text(thinking, pattern)
            mappings.update(new_map)
            block["thinking"] = transformed

    elif block_type == "tool_use":
        inp = block.get("input")
        if inp is not None:
            transformed, new_map = deep_walk_transform(inp, pattern)
            mappings.update(new_map)
            block["input"] = transformed

    elif block_type == "tool_result":
        content = block.get("content")
        if content is not None:
            transformed, new_map = transform_content(content, pattern)
            mappings.update(new_map)
            block["content"] = transformed

    elif block_type in ("redacted_thinking", "image", "document"):
        pass  # skip binary/encrypted

    else:
        # Unknown block type — deep walk except skip keys
        transformed, new_map = deep_walk_transform(block, pattern)
        mappings.update(new_map)
        block = transformed

    return block, mappings


def transform_content(
    content: str | list, pattern: re.Pattern
) -> tuple[str | list, dict[str, str]]:
    """Transform a content field (string or list of blocks)."""
    if isinstance(content, str):
        return transform_text(content, pattern)

    if isinstance(content, list):
        mappings: dict[str, str] = {}
        result: list[Any] = []
        for block in content:
            if isinstance(block, dict):
                transformed, new_map = transform_content_block(block, pattern)
                mappings.update(new_map)
                result.append(transformed)
            elif isinstance(block, str):
                transformed_s, new_map = transform_text(block, pattern)
                mappings.update(new_map)
                result.append(transformed_s)
            else:
                result.append(block)
        return result, mappings

    return content, {}


def transform_messages(
    messages: list[dict], pattern: re.Pattern
) -> tuple[list[dict], dict[str, str]]:
    """Transform messages array."""
    all_mappings: dict[str, str] = {}
    result: list[dict] = []
    for msg in messages:
        msg = dict(msg)
        content = msg.get("content")
        if content is not None:
            transformed, new_map = transform_content(content, pattern)
            all_mappings.update(new_map)
            msg["content"] = transformed
        result.append(msg)
    return result, all_mappings


def transform_request_body(body: dict, pattern: re.Pattern) -> tuple[dict, dict[str, str]]:
    """Transform an Anthropic Messages API request body."""
    body = dict(body)  # shallow copy
    all_mappings: dict[str, str] = {}

    # system (string or list of content blocks)
    system = body.get("system")
    if system is not None:
        transformed, new_map = transform_content(system, pattern)
        all_mappings.update(new_map)
        body["system"] = transformed

    # messages
    messages = body.get("messages")
    if messages is not None:
        transformed_msgs, new_map = transform_messages(messages, pattern)
        all_mappings.update(new_map)
        body["messages"] = transformed_msgs

    # tools[].description
    tools = body.get("tools")
    if tools is not None:
        new_tools: list[dict] = []
        for tool in tools:
            tool = dict(tool)
            desc = tool.get("description", "")
            if isinstance(desc, str) and desc:
                transformed_d, new_map = transform_text(desc, pattern)
                all_mappings.update(new_map)
                tool["description"] = transformed_d
            new_tools.append(tool)
        body["tools"] = new_tools

    return body, all_mappings


# ---------------------------------------------------------------------------
# Response transformation (non-streaming)
# ---------------------------------------------------------------------------
def restore_response_body(body: dict, mappings: dict[str, str]) -> dict:
    """Restore placeholders in a non-streaming response body."""
    return deep_walk_restore(body, mappings)


# ---------------------------------------------------------------------------
# Response transformation (streaming)
# ---------------------------------------------------------------------------
class StreamBuffer:
    """Per-content-block buffer state for streaming restoration."""

    __slots__ = ("block_type", "text_buffer", "json_fragments")

    def __init__(self, block_type: str) -> None:
        self.block_type = block_type
        self.text_buffer: str = ""
        self.json_fragments: list[str] = []


def flush_text_buffer(
    block_index: int,
    new_text: str,
    block_buffers: dict[int, StreamBuffer],
    mappings: dict[str, str],
) -> str:
    """Append new_text to block buffer, restore complete placeholders,
    return text safe to emit (excluding trailing partial placeholder)."""
    buf = block_buffers.get(block_index)
    if buf is None:
        return restore_text(new_text, mappings)

    buf.text_buffer += new_text
    restored = restore_text(buf.text_buffer, mappings)

    partial_match = PARTIAL_PLACEHOLDER_RE.search(restored)
    if partial_match:
        emit_text = restored[: partial_match.start()]
        buf.text_buffer = restored[partial_match.start() :]
    else:
        emit_text = restored
        buf.text_buffer = ""

    return emit_text


def flush_block_stop(
    block_index: int,
    block_buffers: dict[int, StreamBuffer],
    mappings: dict[str, str],
) -> list[tuple[str, dict]]:
    """Flush remaining buffer for a block that just ended."""
    buf = block_buffers.pop(block_index, None)
    if buf is None:
        return [
            (
                "content_block_stop",
                {"type": "content_block_stop", "index": block_index},
            )
        ]

    events: list[tuple[str, dict]] = []

    if buf.block_type == "tool_use" and buf.json_fragments:
        full_json_str = "".join(buf.json_fragments)
        try:
            parsed = json.loads(full_json_str)
            restored = deep_walk_restore(parsed, mappings)
            restored_str = json.dumps(restored)
        except json.JSONDecodeError:
            restored_str = full_json_str
        events.append(
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": block_index,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": restored_str,
                    },
                },
            )
        )
    elif buf.text_buffer:
        # Emit remaining text as-is (no more data coming)
        if buf.block_type == "thinking":
            delta_type = "thinking_delta"
            delta_key = "thinking"
        else:
            delta_type = "text_delta"
            delta_key = "text"
        events.append(
            (
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": block_index,
                    "delta": {"type": delta_type, delta_key: buf.text_buffer},
                },
            )
        )

    events.append(
        (
            "content_block_stop",
            {"type": "content_block_stop", "index": block_index},
        )
    )
    return events


def handle_sse_event(
    event_type: str,
    data: dict,
    block_buffers: dict[int, StreamBuffer],
    mappings: dict[str, str],
) -> list[tuple[str, dict]]:
    """Process one SSE event. Returns list of (event_type, data)
    tuples to emit (may be 0, 1, or multiple)."""
    passthrough = (
        "message_start",
        "message_delta",
        "message_stop",
        "ping",
    )
    if event_type in passthrough:
        return [(event_type, data)]

    if event_type == "content_block_start":
        index = data.get("index", 0)
        content_block = data.get("content_block", {})
        block_type = content_block.get("type", "text")
        block_buffers[index] = StreamBuffer(block_type)

        if block_type == "web_search_tool_result":
            data = deep_walk_restore(data, mappings)

        return [(event_type, data)]

    if event_type == "content_block_delta":
        index = data.get("index", 0)
        delta = data.get("delta", {})
        delta_type = delta.get("type", "")

        if delta_type == "text_delta":
            new_text = delta.get("text", "")
            emit = flush_text_buffer(index, new_text, block_buffers, mappings)
            if emit:
                return [
                    (
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {
                                "type": "text_delta",
                                "text": emit,
                            },
                        },
                    )
                ]
            return []

        if delta_type == "thinking_delta":
            new_text = delta.get("thinking", "")
            emit = flush_text_buffer(index, new_text, block_buffers, mappings)
            if emit:
                return [
                    (
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {
                                "type": "thinking_delta",
                                "thinking": emit,
                            },
                        },
                    )
                ]
            return []

        if delta_type == "input_json_delta":
            partial_json = delta.get("partial_json", "")
            buf = block_buffers.get(index)
            if buf is not None:
                buf.json_fragments.append(partial_json)
            return []

        if delta_type == "citations_delta":
            restored_data = deep_walk_restore(data, mappings)
            return [(event_type, restored_data)]

        # Unknown delta type — pass through
        return [(event_type, data)]

    if event_type == "content_block_stop":
        index = data.get("index", 0)
        return flush_block_stop(index, block_buffers, mappings)

    # Unknown event type — pass through
    return [(event_type, data)]


# ---------------------------------------------------------------------------
# Upstream connection
# ---------------------------------------------------------------------------
def connect_upstream(config: Config, *, streaming: bool = False) -> http.client.HTTPSConnection:
    """Create connection to upstream, optionally tunneled through
    corp proxy."""
    timeout = READ_TIMEOUT_STREAMING if streaming else READ_TIMEOUT_NORMAL
    context = ssl.create_default_context()

    if config.corp_proxy_host:
        conn = http.client.HTTPSConnection(
            config.corp_proxy_host,
            config.corp_proxy_port or 8080,
            timeout=timeout,
            context=context,
        )
        conn.set_tunnel(config.upstream_host, config.upstream_port)
    else:
        conn = http.client.HTTPSConnection(
            config.upstream_host,
            config.upstream_port,
            timeout=timeout,
            context=context,
        )

    return conn


def forward_request(
    conn: http.client.HTTPSConnection,
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
) -> http.client.HTTPResponse:
    """Send request to upstream, return response object."""
    conn.request(method, path, body=body, headers=headers)
    return conn.getresponse()


def _decompress_reader(
    resp: http.client.HTTPResponse,
) -> io.BufferedIOBase | http.client.HTTPResponse:
    """Wrap *resp* in a streaming decompressor if Content-Encoding is set.

    Returns an object with a .readline() method that yields decompressed
    lines.  If the response is not compressed, returns *resp* unchanged.
    """
    encoding = (resp.getheader("Content-Encoding") or "").lower()
    if encoding not in ("gzip", "deflate"):
        return resp
    # wbits: 16+MAX_WBITS for gzip, MAX_WBITS for deflate
    wbits = zlib.MAX_WBITS | 16 if encoding == "gzip" else zlib.MAX_WBITS
    decompressor = zlib.decompressobj(wbits)
    buf = b""

    class _Reader(io.RawIOBase):
        """Thin adapter: read compressed chunks, yield decompressed bytes."""

        def readinto(self, b: bytearray | memoryview) -> int:  # type: ignore[override]
            nonlocal buf
            while not buf:
                chunk = resp.read(8192)
                if not chunk:
                    # Flush remaining data from the decompressor.
                    buf = decompressor.flush()
                    if not buf:
                        return 0
                    break
                buf = decompressor.decompress(chunk)
            n = min(len(b), len(buf))
            b[:n] = buf[:n]
            buf = buf[n:]
            return n

        def readable(self) -> bool:
            return True

    return io.BufferedReader(_Reader(), buffer_size=16384)


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
HOP_BY_HOP = frozenset(
    {
        "host",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "upgrade",
    }
)


class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the proxy."""

    # HTTP/1.1 is required for SSE: clients need proper framing to detect
    # when the response body ends.  Without it (HTTP/1.0), SSE streams
    # stall because the client cannot determine body length.
    protocol_version = "HTTP/1.1"

    # Silence default access log
    def log_message(self, format: str, *args: Any) -> None:
        if self.server_state.config.debug:
            logger.debug(format, *args)

    @property
    def server_state(self) -> ProxyState:
        return self.server.proxy_state  # type: ignore[attr-defined]

    def log_debug(self, msg: str) -> None:
        if self.server_state.config.debug:
            logger.debug(msg)

    def send_error_response(self, status: int, error_type: str, message: str) -> None:
        """Send an Anthropic-format error response."""
        body = json.dumps(
            {
                "type": "error",
                "error": {"type": error_type, "message": message},
            }
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _build_upstream_headers(self) -> dict[str, str]:
        """Extract headers from client request for upstream."""
        headers: dict[str, str] = {}
        for key in self.headers:
            if key.lower() in HOP_BY_HOP:
                continue
            val = self.headers[key]
            if val is not None:
                headers[key] = val
        headers["Host"] = self.server_state.config.upstream_host
        return headers

    def _read_request_body(self) -> bytes:
        """Read the full request body based on Content-Length."""
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            return self.rfile.read(length)
        return b""

    # --- HTTP method handlers ---

    def do_GET(self) -> None:
        """Health check or passthrough."""
        if self.path == "/health":
            state = self.server_state
            mappings = state.get_mappings()
            body = json.dumps(
                {
                    "status": "ok",
                    "mappings_count": len(mappings),
                    "upstream": state.config.upstream_url,
                    "corp_proxy": state.config.corp_proxy_url,
                    "domains_configured": (state.config.url_pattern is not None),
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.forward_passthrough("GET")

    def do_POST(self) -> None:
        """Intercept /v1/messages, passthrough rest."""
        base_path = self.path.split("?")[0].rstrip("/")
        if base_path == "/v1/messages":
            self.handle_messages_post()
        else:
            self.forward_passthrough("POST")

    def do_OPTIONS(self) -> None:
        self.forward_passthrough("OPTIONS")

    def do_PUT(self) -> None:
        self.forward_passthrough("PUT")

    def do_DELETE(self) -> None:
        self.forward_passthrough("DELETE")

    # --- Core logic ---

    def forward_passthrough(self, method: str) -> None:
        """Forward request/response without transformation."""
        config = self.server_state.config
        raw_body = self._read_request_body()
        headers = self._build_upstream_headers()
        upstream_path = config.upstream_path_prefix + self.path

        try:
            conn = connect_upstream(config)
            resp = forward_request(conn, method, upstream_path, headers, raw_body)
        except (ConnectionRefusedError, OSError, socket.gaierror) as exc:
            self.log_debug(f"Upstream connection error: {exc}")
            self.send_error_response(
                502,
                "api_error",
                "Link proxy: could not connect to upstream",
            )
            return
        except TimeoutError:
            self.send_error_response(
                504,
                "timeout_error",
                "Link proxy: upstream connection timed out",
            )
            return

        try:
            resp_body = resp.read()
            self.send_response(resp.status)
            for key, val in resp.getheaders():
                low = key.lower()
                if low in ("transfer-encoding", "connection", "keep-alive"):
                    continue
                if low == "content-length":
                    continue
                self.send_header(key, val)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
        except Exception as exc:
            self.log_debug(f"Passthrough error: {exc}")
        finally:
            conn.close()

    def handle_messages_post(self) -> None:
        """Transform request, forward, handle response."""
        config = self.server_state.config

        raw_body = self._read_request_body()
        try:
            body = json.loads(raw_body)
        except (json.JSONDecodeError, ValueError):
            self.send_error_response(
                400,
                "invalid_request_error",
                "Link proxy: request body is not valid JSON",
            )
            return

        is_streaming = body.get("stream", False)

        # Transform request
        try:
            if config.url_pattern is not None:
                transformed_body, new_mappings = transform_request_body(body, config.url_pattern)
                self.server_state.add_mappings(new_mappings)
                if new_mappings:
                    self.log_debug(f"Transformed: {len(new_mappings)} new mappings")
            else:
                transformed_body = body
        except Exception:
            logger.error("Request transform error:\n%s", traceback.format_exc())
            self.send_error_response(
                500,
                "api_error",
                "Link proxy: internal error during transformation",
            )
            return

        # Forward to upstream
        transformed_bytes = json.dumps(transformed_body).encode()
        headers = self._build_upstream_headers()
        headers["Content-Length"] = str(len(transformed_bytes))
        upstream_path = config.upstream_path_prefix + self.path

        try:
            conn = connect_upstream(config, streaming=is_streaming)
            resp = forward_request(conn, "POST", upstream_path, headers, transformed_bytes)
        except (ConnectionRefusedError, OSError, socket.gaierror) as exc:
            self.log_debug(f"Upstream connection error: {exc}")
            self.send_error_response(
                502,
                "api_error",
                "Link proxy: could not connect to upstream",
            )
            return
        except TimeoutError:
            self.send_error_response(
                504,
                "timeout_error",
                "Link proxy: upstream connection timed out",
            )
            return

        try:
            if is_streaming and resp.status == 200:
                self.stream_response(conn, resp)
            else:
                self._handle_buffered_response(conn, resp)
        except Exception:
            logger.error("Response handling error:\n%s", traceback.format_exc())
        finally:
            conn.close()

    def _handle_buffered_response(
        self,
        conn: http.client.HTTPSConnection,
        resp: http.client.HTTPResponse,
    ) -> None:
        """Handle a non-streaming (buffered) response."""
        resp_body = _decompress_reader(resp).read()
        mappings = self.server_state.get_mappings()

        if resp_body and mappings:
            try:
                resp_json = json.loads(resp_body)
                restored = restore_response_body(resp_json, mappings)
                resp_body = json.dumps(restored).encode()
            except (json.JSONDecodeError, ValueError):
                pass  # not JSON, forward as-is

        self.send_response(resp.status)
        for key, val in resp.getheaders():
            low = key.lower()
            if low in (
                "transfer-encoding",
                "connection",
                "keep-alive",
                "content-length",
                "content-encoding",
            ):
                continue
            self.send_header(key, val)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def stream_response(
        self,
        conn: http.client.HTTPSConnection,
        resp: http.client.HTTPResponse,
    ) -> None:
        """Handle SSE streaming response with buffering."""
        reader = _decompress_reader(resp)
        mappings = self.server_state.get_mappings()
        block_buffers: dict[int, StreamBuffer] = {}

        self.send_response(resp.status)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        # Close connection after streaming so the client detects end-of-body.
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()

        current_event_type: str | None = None
        current_data_lines: list[str] = []

        def emit_sse(ev_type: str, ev_data: dict) -> None:
            """Write one SSE event to the client."""
            line = f"event: {ev_type}\ndata: {json.dumps(ev_data)}\n\n"
            self.wfile.write(line.encode())
            self.wfile.flush()

        def process_sse_block() -> None:
            nonlocal current_event_type, current_data_lines
            if current_event_type is None and not current_data_lines:
                return

            ev_type = current_event_type or ""
            data_str = "\n".join(current_data_lines)

            current_event_type = None
            current_data_lines = []

            if not data_str:
                if ev_type:
                    self.wfile.write(f"event: {ev_type}\n\n".encode())
                    self.wfile.flush()
                return

            try:
                ev_data = json.loads(data_str)
            except (json.JSONDecodeError, ValueError):
                out = ""
                if ev_type:
                    out += f"event: {ev_type}\n"
                out += f"data: {data_str}\n\n"
                self.wfile.write(out.encode())
                self.wfile.flush()
                return

            # Get fresh mappings (may have grown during request)
            fresh = self.server_state.get_mappings()
            fresh.update(mappings)

            try:
                to_emit = handle_sse_event(ev_type, ev_data, block_buffers, fresh)
                for out_type, out_data in to_emit:
                    emit_sse(out_type, out_data)
            except Exception:
                logger.error("SSE event error:\n%s", traceback.format_exc())
                emit_sse(ev_type, ev_data)

        try:
            while True:
                raw_line = reader.readline()
                if not raw_line:
                    break

                line = raw_line.decode("utf-8", errors="replace")
                line = line.rstrip("\r\n")

                if line.startswith("event:"):
                    if current_event_type is not None or current_data_lines:
                        process_sse_block()
                    current_event_type = line[len("event:") :].strip()

                elif line.startswith("data:"):
                    current_data_lines.append(line[len("data:") :].strip())

                elif line == "":
                    process_sse_block()

                else:
                    # Comment or unknown — pass through
                    self.wfile.write((line + "\n").encode())
                    self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError):
            self.log_debug("Client disconnected during streaming")
        except Exception:
            logger.error("Stream read error:\n%s", traceback.format_exc())

        # Flush any final pending event
        try:
            process_sse_block()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
class ProxyServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with attached proxy state."""

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        proxy_state: ProxyState,
    ) -> None:
        self.proxy_state = proxy_state
        super().__init__(server_address, handler_class)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Parse config, initialize state, start server."""
    config = load_config()
    print_config(config)

    state = ProxyState(config)
    existing = load_mappings()
    state.add_mappings(existing)

    server = ProxyServer(("127.0.0.1", config.port), ProxyHandler, state)

    def shutdown_handler(signum: int, _frame: Any) -> None:
        name = signal.Signals(signum).name
        print(
            f"\n[link-proxy] Received {name}, shutting down...",
            file=sys.stderr,
        )
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    print(
        f"[link-proxy] Listening on http://127.0.0.1:{config.port}",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
        print("[link-proxy] Server stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
