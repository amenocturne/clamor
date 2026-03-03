"""Unit tests for link-proxy proxy module.

Tests the pure transformation functions: deep walk, content block
transforms, request/response body transforms, streaming buffer
algorithms, and SSE event handling.

Does NOT test HTTP handler internals or upstream connections.
"""

import json
import threading

import pytest

from main import build_url_pattern, url_to_placeholder
from proxy import (
    PARTIAL_PLACEHOLDER_RE,
    Config,
    ProxyState,
    StreamBuffer,
    deep_walk_restore,
    deep_walk_transform,
    flush_block_stop,
    flush_text_buffer,
    handle_sse_event,
    restore_response_body,
    transform_content_block,
    transform_request_body,
)

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------
TEST_DOMAINS = ["internal.corp.net"]
URL_WIKI = "https://wiki.internal.corp.net/docs/architecture"
URL_JIRA = "https://jira.internal.corp.net/browse/PROJ-123"

# Pre-computed deterministic placeholders
PLACEHOLDER_WIKI, HASH_WIKI = url_to_placeholder(URL_WIKI)
PLACEHOLDER_JIRA, HASH_JIRA = url_to_placeholder(URL_JIRA)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def pattern():
    """Compiled URL pattern for test domains."""
    p = build_url_pattern(TEST_DOMAINS)
    assert p is not None
    return p


@pytest.fixture
def mappings():
    """Hash -> URL mappings for the two test URLs."""
    return {HASH_WIKI: URL_WIKI, HASH_JIRA: URL_JIRA}


@pytest.fixture
def dummy_config():
    """Minimal Config for ProxyState tests (no real upstream)."""
    return Config(
        port=18923,
        upstream_url="https://api.anthropic.com",
        upstream_host="api.anthropic.com",
        upstream_port=443,
        upstream_path_prefix="",
        corp_proxy_url=None,
        corp_proxy_host=None,
        corp_proxy_port=None,
        url_pattern=build_url_pattern(TEST_DOMAINS),
        debug=False,
    )


# ===================================================================
# 1. deep_walk_transform / deep_walk_restore
# ===================================================================
class TestDeepWalkTransform:
    def test_simple_string(self, pattern):
        result, m = deep_walk_transform(f"see {URL_WIKI} for details", pattern)
        assert PLACEHOLDER_WIKI in result
        assert URL_WIKI not in result
        assert HASH_WIKI in m
        assert m[HASH_WIKI] == URL_WIKI

    def test_nested_dict(self, pattern):
        obj = {"a": {"b": f"link: {URL_JIRA}"}}
        result, m = deep_walk_transform(obj, pattern)
        assert PLACEHOLDER_JIRA in result["a"]["b"]
        assert HASH_JIRA in m

    def test_nested_list(self, pattern):
        obj = [f"url: {URL_WIKI}", [f"nested {URL_JIRA}"]]
        result, m = deep_walk_transform(obj, pattern)
        assert PLACEHOLDER_WIKI in result[0]
        assert PLACEHOLDER_JIRA in result[1][0]
        assert len(m) == 2

    def test_mixed_nested_structure(self, pattern):
        """List of dicts containing lists."""
        obj = [
            {"texts": [f"see {URL_WIKI}", f"ticket {URL_JIRA}"]},
            {"other": "no urls here"},
        ]
        result, m = deep_walk_transform(obj, pattern)
        assert PLACEHOLDER_WIKI in result[0]["texts"][0]
        assert PLACEHOLDER_JIRA in result[0]["texts"][1]
        assert result[1]["other"] == "no urls here"
        assert len(m) == 2

    def test_skip_keys(self, pattern):
        """Values under SKIP_KEYS must NOT be transformed."""
        obj = {
            "data": f"has url {URL_WIKI}",
            "encrypted_content": f"has url {URL_JIRA}",
            "signature": f"sig with {URL_WIKI}",
            "encrypted_index": f"idx with {URL_JIRA}",
            "normal_key": f"url: {URL_WIKI}",
        }
        result, m = deep_walk_transform(obj, pattern)
        # Skipped keys preserve original values
        assert result["data"] == f"has url {URL_WIKI}"
        assert result["encrypted_content"] == f"has url {URL_JIRA}"
        assert result["signature"] == f"sig with {URL_WIKI}"
        assert result["encrypted_index"] == f"idx with {URL_JIRA}"
        # Normal key is transformed
        assert PLACEHOLDER_WIKI in result["normal_key"]
        # Only the normal_key mapping should be present
        assert len(m) == 1

    def test_non_string_passthrough(self, pattern):
        obj = {"count": 42, "ratio": 3.14, "active": True, "val": None}
        result, m = deep_walk_transform(obj, pattern)
        assert result == obj
        assert m == {}

    def test_empty_structures(self, pattern):
        result_dict, m1 = deep_walk_transform({}, pattern)
        result_list, m2 = deep_walk_transform([], pattern)
        result_str, m3 = deep_walk_transform("", pattern)
        assert result_dict == {}
        assert result_list == []
        assert result_str == ""
        assert m1 == m2 == m3 == {}

    def test_does_not_mutate_original(self, pattern):
        original = {"key": f"url: {URL_WIKI}"}
        deep_walk_transform(original, pattern)
        assert URL_WIKI in original["key"]


class TestDeepWalkRestore:
    def test_simple_string(self, mappings):
        text = f"see {PLACEHOLDER_WIKI} for details"
        result = deep_walk_restore(text, mappings)
        assert URL_WIKI in result
        assert PLACEHOLDER_WIKI not in result

    def test_nested_dict(self, mappings):
        obj = {"a": {"b": f"link: {PLACEHOLDER_JIRA}"}}
        result = deep_walk_restore(obj, mappings)
        assert URL_JIRA in result["a"]["b"]

    def test_skip_keys(self, mappings):
        obj = {
            "data": f"has {PLACEHOLDER_WIKI}",
            "normal": f"has {PLACEHOLDER_WIKI}",
        }
        result = deep_walk_restore(obj, mappings)
        assert PLACEHOLDER_WIKI in result["data"]  # skipped
        assert URL_WIKI in result["normal"]  # restored

    def test_non_string_passthrough(self, mappings):
        assert deep_walk_restore(42, mappings) == 42
        assert deep_walk_restore(None, mappings) is None
        assert deep_walk_restore(True, mappings) is True

    def test_empty_mappings(self):
        text = f"see {PLACEHOLDER_WIKI}"
        assert deep_walk_restore(text, {}) == text


# ===================================================================
# 2. transform_content_block
# ===================================================================
class TestTransformContentBlock:
    def test_text_block(self, pattern):
        block = {"type": "text", "text": f"visit {URL_WIKI}"}
        result, m = transform_content_block(block, pattern)
        assert result["type"] == "text"
        assert PLACEHOLDER_WIKI in result["text"]
        assert URL_WIKI not in result["text"]
        assert HASH_WIKI in m

    def test_thinking_block(self, pattern):
        block = {"type": "thinking", "thinking": f"URL here: {URL_JIRA}"}
        result, m = transform_content_block(block, pattern)
        assert PLACEHOLDER_JIRA in result["thinking"]
        assert HASH_JIRA in m

    def test_thinking_block_preserves_signature(self, pattern):
        block = {
            "type": "thinking",
            "thinking": f"URL here: {URL_JIRA}",
            "signature": "some_sig_value",
        }
        result, m = transform_content_block(block, pattern)
        assert result["signature"] == "some_sig_value"

    def test_tool_use_block(self, pattern):
        block = {
            "type": "tool_use",
            "id": "toolu_123",
            "name": "Read",
            "input": {"file_path": "/foo"},
        }
        result, m = transform_content_block(block, pattern)
        assert result["type"] == "tool_use"
        assert result["id"] == "toolu_123"
        assert result["input"]["file_path"] == "/foo"
        assert m == {}

    def test_tool_use_with_urls_in_input(self, pattern):
        block = {
            "type": "tool_use",
            "id": "toolu_456",
            "name": "WebFetch",
            "input": {"url": URL_WIKI, "note": f"see also {URL_JIRA}"},
        }
        result, m = transform_content_block(block, pattern)
        assert PLACEHOLDER_WIKI in result["input"]["url"]
        assert PLACEHOLDER_JIRA in result["input"]["note"]
        assert len(m) == 2

    def test_tool_result_string_content(self, pattern):
        block = {
            "type": "tool_result",
            "tool_use_id": "toolu_123",
            "content": f"File at {URL_WIKI} contains the docs.",
        }
        result, m = transform_content_block(block, pattern)
        assert PLACEHOLDER_WIKI in result["content"]
        assert HASH_WIKI in m

    def test_tool_result_list_content(self, pattern):
        block = {
            "type": "tool_result",
            "tool_use_id": "toolu_123",
            "content": [
                {"type": "text", "text": f"Found: {URL_WIKI}"},
                {"type": "text", "text": f"Also: {URL_JIRA}"},
            ],
        }
        result, m = transform_content_block(block, pattern)
        assert PLACEHOLDER_WIKI in result["content"][0]["text"]
        assert PLACEHOLDER_JIRA in result["content"][1]["text"]
        assert len(m) == 2

    def test_skip_redacted_thinking(self, pattern):
        block = {"type": "redacted_thinking", "data": f"secret {URL_WIKI}"}
        result, m = transform_content_block(block, pattern)
        assert result == block
        assert m == {}

    def test_skip_image(self, pattern):
        block = {
            "type": "image",
            "source": {"type": "base64", "data": "abc123..."},
        }
        result, m = transform_content_block(block, pattern)
        assert result["source"]["data"] == "abc123..."
        assert m == {}

    def test_skip_document(self, pattern):
        block = {
            "type": "document",
            "source": {"type": "base64", "data": "pdf_data..."},
        }
        result, m = transform_content_block(block, pattern)
        assert result["source"]["data"] == "pdf_data..."
        assert m == {}

    def test_unknown_block_type_deep_walks(self, pattern):
        block = {
            "type": "custom_block",
            "content": f"url: {URL_WIKI}",
            "nested": {"field": f"another: {URL_JIRA}"},
        }
        result, m = transform_content_block(block, pattern)
        assert PLACEHOLDER_WIKI in result["content"]
        assert PLACEHOLDER_JIRA in result["nested"]["field"]
        assert len(m) == 2

    def test_does_not_mutate_original_block(self, pattern):
        block = {"type": "text", "text": f"visit {URL_WIKI}"}
        transform_content_block(block, pattern)
        assert URL_WIKI in block["text"]


# ===================================================================
# 3. transform_request_body
# ===================================================================
class TestTransformRequestBody:
    def test_full_request(self, pattern):
        """Full Messages API request with system, messages, tools."""
        body = {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "system": f"You help with {URL_WIKI}",
            "messages": [
                {"role": "user", "content": f"Read {URL_WIKI} please"},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": f"I found {URL_JIRA}"},
                        {
                            "type": "tool_use",
                            "id": "toolu_1",
                            "name": "Read",
                            "input": {"file_path": "/tmp/file.md"},
                        },
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "content": f"Content mentioning {URL_WIKI}",
                        }
                    ],
                },
            ],
            "tools": [
                {
                    "name": "WebFetch",
                    "description": f"Fetches from {URL_WIKI} and more",
                    "input_schema": {"type": "object"},
                }
            ],
        }
        result, m = transform_request_body(body, pattern)

        # System transformed
        assert PLACEHOLDER_WIKI in result["system"]
        assert URL_WIKI not in result["system"]

        # User message (string content)
        assert PLACEHOLDER_WIKI in result["messages"][0]["content"]

        # Assistant text block
        assert PLACEHOLDER_JIRA in result["messages"][1]["content"][0]["text"]

        # Tool result content
        assert PLACEHOLDER_WIKI in result["messages"][2]["content"][0]["content"]

        # Tool description
        assert PLACEHOLDER_WIKI in result["tools"][0]["description"]

        # Model and max_tokens unchanged
        assert result["model"] == "claude-sonnet-4-20250514"
        assert result["max_tokens"] == 1024

    def test_system_as_list(self, pattern):
        body = {
            "system": [
                {"type": "text", "text": f"Help with {URL_WIKI}"},
                {"type": "text", "text": "No URLs here"},
            ],
            "messages": [],
        }
        result, m = transform_request_body(body, pattern)
        assert PLACEHOLDER_WIKI in result["system"][0]["text"]
        assert result["system"][1]["text"] == "No URLs here"

    def test_empty_fields(self, pattern):
        body = {"model": "claude-sonnet-4-20250514", "max_tokens": 100}
        result, m = transform_request_body(body, pattern)
        assert result["model"] == "claude-sonnet-4-20250514"
        assert m == {}

    def test_missing_fields(self, pattern):
        body = {}
        result, m = transform_request_body(body, pattern)
        assert result == {}
        assert m == {}

    def test_tool_description_with_urls(self, pattern):
        body = {
            "tools": [
                {
                    "name": "SearchDocs",
                    "description": f"Searches {URL_WIKI} and {URL_JIRA}",
                    "input_schema": {"type": "object"},
                }
            ],
        }
        result, m = transform_request_body(body, pattern)
        desc = result["tools"][0]["description"]
        assert PLACEHOLDER_WIKI in desc
        assert PLACEHOLDER_JIRA in desc
        assert len(m) == 2


# ===================================================================
# 4. restore_response_body (non-streaming)
# ===================================================================
class TestRestoreResponseBody:
    def test_full_response(self, mappings):
        body = {
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": f"Found at {PLACEHOLDER_WIKI}"},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Read",
                    "input": {"file_path": f"path/{PLACEHOLDER_JIRA}"},
                },
            ],
            "model": "claude-sonnet-4-20250514",
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        result = restore_response_body(body, mappings)
        assert URL_WIKI in result["content"][0]["text"]
        assert PLACEHOLDER_WIKI not in result["content"][0]["text"]
        # tool_use input is restored (not in SKIP_KEYS path)
        assert URL_JIRA in result["content"][1]["input"]["file_path"]
        # Non-string fields unchanged
        assert result["usage"]["input_tokens"] == 100

    def test_nested_tool_use_results(self, mappings):
        body = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "Bash",
                    "input": {
                        "command": f"curl {PLACEHOLDER_WIKI}",
                        "args": [f"--header {PLACEHOLDER_JIRA}"],
                    },
                }
            ]
        }
        result = restore_response_body(body, mappings)
        assert URL_WIKI in result["content"][0]["input"]["command"]
        assert URL_JIRA in result["content"][0]["input"]["args"][0]

    def test_empty_mappings(self):
        body = {"content": [{"type": "text", "text": "hello"}]}
        result = restore_response_body(body, {})
        assert result["content"][0]["text"] == "hello"


# ===================================================================
# 5. flush_text_buffer
# ===================================================================
class TestFlushTextBuffer:
    def test_normal_text_no_placeholders(self, mappings):
        """Normal text without placeholders passes through immediately."""
        buffers = {0: StreamBuffer("text")}
        result = flush_text_buffer(0, "Hello world", buffers, mappings)
        assert result == "Hello world"
        assert buffers[0].text_buffer == ""

    def test_complete_placeholder_single_chunk(self, mappings):
        """Complete placeholder in a single chunk is restored immediately."""
        buffers = {0: StreamBuffer("text")}
        result = flush_text_buffer(0, f"see {PLACEHOLDER_WIKI} here", buffers, mappings)
        assert URL_WIKI in result
        assert PLACEHOLDER_WIKI not in result
        assert buffers[0].text_buffer == ""

    def test_placeholder_split_across_chunks(self, mappings):
        """Placeholder split across two chunks: first buffers, second restores."""
        buffers = {0: StreamBuffer("text")}

        # First chunk: partial placeholder at end
        part1 = "[InternalLink_wiki"
        result1 = flush_text_buffer(0, f"see {part1}", buffers, mappings)
        # "see " is emitted, partial is buffered
        assert result1 == "see "
        assert buffers[0].text_buffer == part1

        # Second chunk: rest of placeholder
        part2 = f"_{HASH_WIKI}] here"
        result2 = flush_text_buffer(0, part2, buffers, mappings)
        assert URL_WIKI in result2
        assert "here" in result2

    def test_multiple_placeholders_one_chunk(self, mappings):
        """Multiple complete placeholders in one chunk all get restored."""
        buffers = {0: StreamBuffer("text")}
        text = f"A: {PLACEHOLDER_WIKI} B: {PLACEHOLDER_JIRA}"
        result = flush_text_buffer(0, text, buffers, mappings)
        assert URL_WIKI in result
        assert URL_JIRA in result

    def test_partial_placeholder_at_end_buffered(self, mappings):
        """Partial placeholder at end of chunk stays buffered."""
        buffers = {0: StreamBuffer("text")}
        result = flush_text_buffer(0, "text [Internal", buffers, mappings)
        assert result == "text "
        assert buffers[0].text_buffer == "[Internal"

    def test_just_opening_bracket_buffered(self, mappings):
        """A single '[' at the end triggers buffering."""
        buffers = {0: StreamBuffer("text")}
        result = flush_text_buffer(0, "end [", buffers, mappings)
        assert result == "end "
        assert buffers[0].text_buffer == "["

    def test_empty_new_text_with_existing_buffer(self, mappings):
        """Empty new_text added to existing buffer returns empty if still partial."""
        buffers = {0: StreamBuffer("text")}
        buffers[0].text_buffer = "[Internal"
        result = flush_text_buffer(0, "", buffers, mappings)
        assert result == ""
        assert buffers[0].text_buffer == "[Internal"

    def test_no_buffer_for_block(self, mappings):
        """When block_index not in block_buffers, restore directly."""
        buffers: dict[int, StreamBuffer] = {}
        result = flush_text_buffer(0, f"text {PLACEHOLDER_WIKI}", buffers, mappings)
        assert URL_WIKI in result

    def test_bracket_mid_text_not_buffered(self, mappings):
        """A '[' followed by non-matching characters then ']' passes through."""
        buffers = {0: StreamBuffer("text")}
        result = flush_text_buffer(0, "array[0] = 1", buffers, mappings)
        # The ']' closes it so no partial, everything emitted
        assert "array[0] = 1" == result

    def test_progressive_accumulation(self, mappings):
        """Simulate streaming the placeholder character by character."""
        buffers = {0: StreamBuffer("text")}
        placeholder = PLACEHOLDER_WIKI
        emitted = []

        # Send prefix text first
        r = flush_text_buffer(0, "prefix ", buffers, mappings)
        emitted.append(r)

        # Send placeholder one char at a time
        for ch in placeholder:
            r = flush_text_buffer(0, ch, buffers, mappings)
            emitted.append(r)

        # Send suffix
        r = flush_text_buffer(0, " suffix", buffers, mappings)
        emitted.append(r)

        full = "".join(emitted)
        assert URL_WIKI in full
        assert PLACEHOLDER_WIKI not in full
        assert "prefix " in full
        assert " suffix" in full


# ===================================================================
# 6. flush_block_stop
# ===================================================================
class TestFlushBlockStop:
    def test_text_block_with_remaining_buffer(self, mappings):
        """Text block with remaining text buffer emits text_delta then stop."""
        buffers = {0: StreamBuffer("text")}
        buffers[0].text_buffer = "leftover text"
        events = flush_block_stop(0, buffers, mappings)

        assert len(events) == 2
        # First event: text_delta with remaining buffer
        ev_type, ev_data = events[0]
        assert ev_type == "content_block_delta"
        assert ev_data["delta"]["type"] == "text_delta"
        assert ev_data["delta"]["text"] == "leftover text"
        # Second event: content_block_stop
        assert events[1][0] == "content_block_stop"
        # Buffer removed
        assert 0 not in buffers

    def test_thinking_block_with_remaining_buffer(self, mappings):
        """Thinking block with remaining buffer emits thinking_delta then stop."""
        buffers = {0: StreamBuffer("thinking")}
        buffers[0].text_buffer = "remaining thought"
        events = flush_block_stop(0, buffers, mappings)

        assert len(events) == 2
        ev_type, ev_data = events[0]
        assert ev_type == "content_block_delta"
        assert ev_data["delta"]["type"] == "thinking_delta"
        assert ev_data["delta"]["thinking"] == "remaining thought"
        assert events[1][0] == "content_block_stop"

    def test_tool_use_block_valid_json(self, mappings):
        """Tool use block reassembles JSON, restores, emits input_json_delta."""
        buffers = {0: StreamBuffer("tool_use")}
        tool_input = {"url": PLACEHOLDER_WIKI, "count": 5}
        json_str = json.dumps(tool_input)
        # Split JSON into fragments
        buffers[0].json_fragments = [json_str[:10], json_str[10:]]

        events = flush_block_stop(0, buffers, mappings)

        assert len(events) == 2
        ev_type, ev_data = events[0]
        assert ev_type == "content_block_delta"
        assert ev_data["delta"]["type"] == "input_json_delta"
        restored_json = json.loads(ev_data["delta"]["partial_json"])
        assert restored_json["url"] == URL_WIKI
        assert restored_json["count"] == 5
        assert events[1][0] == "content_block_stop"

    def test_tool_use_block_invalid_json(self, mappings):
        """Tool use block with invalid JSON emits raw string."""
        buffers = {0: StreamBuffer("tool_use")}
        buffers[0].json_fragments = ['{"broken": ']

        events = flush_block_stop(0, buffers, mappings)

        assert len(events) == 2
        ev_type, ev_data = events[0]
        assert ev_type == "content_block_delta"
        assert ev_data["delta"]["partial_json"] == '{"broken": '
        assert events[1][0] == "content_block_stop"

    def test_no_buffer_for_block(self, mappings):
        """Block not in buffers produces just content_block_stop."""
        buffers: dict[int, StreamBuffer] = {}
        events = flush_block_stop(5, buffers, mappings)
        assert len(events) == 1
        assert events[0][0] == "content_block_stop"
        assert events[0][1]["index"] == 5

    def test_empty_text_buffer(self, mappings):
        """Block with empty text_buffer and no json_fragments: just stop."""
        buffers = {0: StreamBuffer("text")}
        events = flush_block_stop(0, buffers, mappings)
        assert len(events) == 1
        assert events[0][0] == "content_block_stop"

    def test_buffer_removed_after_stop(self, mappings):
        """Buffer is removed from dict after flush_block_stop."""
        buffers = {0: StreamBuffer("text")}
        buffers[0].text_buffer = "some text"
        flush_block_stop(0, buffers, mappings)
        assert 0 not in buffers


# ===================================================================
# 7. handle_sse_event
# ===================================================================
class TestHandleSSEEvent:
    def test_passthrough_message_start(self, mappings):
        data = {"type": "message_start", "message": {"id": "msg_1"}}
        events = handle_sse_event("message_start", data, {}, mappings)
        assert len(events) == 1
        assert events[0] == ("message_start", data)

    def test_passthrough_message_delta(self, mappings):
        data = {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}
        events = handle_sse_event("message_delta", data, {}, mappings)
        assert events == [("message_delta", data)]

    def test_passthrough_message_stop(self, mappings):
        data = {"type": "message_stop"}
        events = handle_sse_event("message_stop", data, {}, mappings)
        assert events == [("message_stop", data)]

    def test_passthrough_ping(self, mappings):
        data = {"type": "ping"}
        events = handle_sse_event("ping", data, {}, mappings)
        assert events == [("ping", data)]

    def test_content_block_start_text(self, mappings):
        """content_block_start with text block creates StreamBuffer."""
        buffers: dict[int, StreamBuffer] = {}
        data = {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "text", "text": ""},
        }
        events = handle_sse_event("content_block_start", data, buffers, mappings)
        assert len(events) == 1
        assert events[0][0] == "content_block_start"
        assert 0 in buffers
        assert buffers[0].block_type == "text"

    def test_content_block_start_thinking(self, mappings):
        buffers: dict[int, StreamBuffer] = {}
        data = {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "thinking", "thinking": ""},
        }
        handle_sse_event("content_block_start", data, buffers, mappings)
        assert 1 in buffers
        assert buffers[1].block_type == "thinking"

    def test_content_block_start_tool_use(self, mappings):
        buffers: dict[int, StreamBuffer] = {}
        data = {
            "type": "content_block_start",
            "index": 2,
            "content_block": {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "Read",
                "input": {},
            },
        }
        handle_sse_event("content_block_start", data, buffers, mappings)
        assert 2 in buffers
        assert buffers[2].block_type == "tool_use"

    def test_content_block_start_web_search_result(self, mappings):
        """web_search_tool_result block gets restored and passed through."""
        buffers: dict[int, StreamBuffer] = {}
        data = {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "web_search_tool_result",
                "search_results": [
                    {
                        "title": f"Page at {PLACEHOLDER_WIKI}",
                        "url": PLACEHOLDER_JIRA,
                    }
                ],
            },
        }
        events = handle_sse_event("content_block_start", data, buffers, mappings)
        assert len(events) == 1
        result_data = events[0][1]
        sr = result_data["content_block"]["search_results"][0]
        assert URL_WIKI in sr["title"]
        assert URL_JIRA == sr["url"]

    def test_content_block_delta_text(self, mappings):
        """text_delta uses flush_text_buffer."""
        buffers = {0: StreamBuffer("text")}
        data = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": f"see {PLACEHOLDER_WIKI}"},
        }
        events = handle_sse_event("content_block_delta", data, buffers, mappings)
        assert len(events) == 1
        emitted_text = events[0][1]["delta"]["text"]
        assert URL_WIKI in emitted_text

    def test_content_block_delta_text_empty_emit(self, mappings):
        """text_delta that buffers everything returns no events."""
        buffers = {0: StreamBuffer("text")}
        data = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "[Internal"},
        }
        events = handle_sse_event("content_block_delta", data, buffers, mappings)
        assert events == []

    def test_content_block_delta_thinking(self, mappings):
        """thinking_delta uses flush_text_buffer with thinking key."""
        buffers = {1: StreamBuffer("thinking")}
        data = {
            "type": "content_block_delta",
            "index": 1,
            "delta": {
                "type": "thinking_delta",
                "thinking": f"url: {PLACEHOLDER_JIRA}",
            },
        }
        events = handle_sse_event("content_block_delta", data, buffers, mappings)
        assert len(events) == 1
        assert events[0][1]["delta"]["type"] == "thinking_delta"
        assert URL_JIRA in events[0][1]["delta"]["thinking"]

    def test_content_block_delta_input_json(self, mappings):
        """input_json_delta accumulates fragments, emits nothing."""
        buffers = {2: StreamBuffer("tool_use")}
        data = {
            "type": "content_block_delta",
            "index": 2,
            "delta": {
                "type": "input_json_delta",
                "partial_json": '{"file_path":',
            },
        }
        events = handle_sse_event("content_block_delta", data, buffers, mappings)
        assert events == []
        assert buffers[2].json_fragments == ['{"file_path":']

    def test_content_block_delta_input_json_accumulates(self, mappings):
        """Multiple input_json_delta events accumulate in order."""
        buffers = {2: StreamBuffer("tool_use")}
        fragments = ['{"a":', '"b"}']
        for frag in fragments:
            data = {
                "type": "content_block_delta",
                "index": 2,
                "delta": {
                    "type": "input_json_delta",
                    "partial_json": frag,
                },
            }
            events = handle_sse_event("content_block_delta", data, buffers, mappings)
            assert events == []
        assert buffers[2].json_fragments == fragments

    def test_content_block_delta_citations(self, mappings):
        """citations_delta gets deep_walk_restore applied."""
        buffers = {0: StreamBuffer("text")}
        data = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {
                "type": "citations_delta",
                "citation": {"url": PLACEHOLDER_WIKI},
            },
        }
        events = handle_sse_event("content_block_delta", data, buffers, mappings)
        assert len(events) == 1
        assert URL_WIKI in events[0][1]["delta"]["citation"]["url"]

    def test_content_block_delta_unknown_type(self, mappings):
        """Unknown delta type passes through."""
        buffers = {0: StreamBuffer("text")}
        data = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "mystery_delta", "stuff": "value"},
        }
        events = handle_sse_event("content_block_delta", data, buffers, mappings)
        assert events == [("content_block_delta", data)]

    def test_content_block_stop(self, mappings):
        """content_block_stop calls flush_block_stop."""
        buffers = {0: StreamBuffer("text")}
        buffers[0].text_buffer = "remaining"
        data = {"type": "content_block_stop", "index": 0}
        events = handle_sse_event("content_block_stop", data, buffers, mappings)
        # Should emit text_delta + content_block_stop
        assert len(events) == 2
        assert events[0][1]["delta"]["text"] == "remaining"
        assert events[1][0] == "content_block_stop"
        assert 0 not in buffers

    def test_unknown_event_type(self, mappings):
        """Unknown event type passes through."""
        data = {"type": "unknown_event", "payload": 42}
        events = handle_sse_event("unknown_event", data, {}, mappings)
        assert events == [("unknown_event", data)]


# ===================================================================
# 8. StreamBuffer
# ===================================================================
class TestStreamBuffer:
    def test_initial_state(self):
        buf = StreamBuffer("text")
        assert buf.block_type == "text"
        assert buf.text_buffer == ""
        assert buf.json_fragments == []

    def test_block_type_preserved(self):
        for bt in ("text", "thinking", "tool_use"):
            buf = StreamBuffer(bt)
            assert buf.block_type == bt

    def test_text_buffer_accumulation(self):
        buf = StreamBuffer("text")
        buf.text_buffer += "hello "
        buf.text_buffer += "world"
        assert buf.text_buffer == "hello world"

    def test_json_fragment_accumulation(self):
        buf = StreamBuffer("tool_use")
        buf.json_fragments.append('{"a":')
        buf.json_fragments.append('"b"}')
        assert "".join(buf.json_fragments) == '{"a":"b"}'


# ===================================================================
# 9. ProxyState
# ===================================================================
class TestProxyState:
    def test_empty_mappings_initially(self, dummy_config):
        state = ProxyState(dummy_config)
        assert state.get_mappings() == {}

    def test_add_mappings(self, dummy_config):
        state = ProxyState(dummy_config)
        state.add_mappings({HASH_WIKI: URL_WIKI})
        m = state.get_mappings()
        assert m[HASH_WIKI] == URL_WIKI

    def test_multiple_add_mappings_accumulate(self, dummy_config):
        state = ProxyState(dummy_config)
        state.add_mappings({HASH_WIKI: URL_WIKI})
        state.add_mappings({HASH_JIRA: URL_JIRA})
        m = state.get_mappings()
        assert len(m) == 2
        assert m[HASH_WIKI] == URL_WIKI
        assert m[HASH_JIRA] == URL_JIRA

    def test_add_empty_mappings(self, dummy_config):
        state = ProxyState(dummy_config)
        state.add_mappings({})
        assert state.get_mappings() == {}

    def test_get_mappings_returns_copy(self, dummy_config):
        state = ProxyState(dummy_config)
        state.add_mappings({HASH_WIKI: URL_WIKI})
        m = state.get_mappings()
        m["extra"] = "should not affect state"
        assert "extra" not in state.get_mappings()

    def test_thread_safety(self, dummy_config):
        """Concurrent add_mappings calls don't lose data."""
        state = ProxyState(dummy_config)
        errors = []

        def add_batch(start: int, count: int):
            try:
                for i in range(start, start + count):
                    state.add_mappings({f"hash_{i}": f"url_{i}"})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=add_batch, args=(i * 100, 100)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        m = state.get_mappings()
        assert len(m) == 1000


# ===================================================================
# 10. Integration: round-trip transform -> restore
# ===================================================================
class TestRoundTrip:
    def test_request_transform_then_restore(self, pattern, mappings):
        """Transform a request body, then restore placeholders: lossless."""
        body = {
            "system": f"Internal wiki: {URL_WIKI}",
            "messages": [
                {
                    "role": "user",
                    "content": f"Check {URL_WIKI} and {URL_JIRA}",
                },
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "text": f"Found {URL_JIRA} in the ticket",
                        }
                    ],
                },
            ],
            "tools": [
                {
                    "name": "Fetch",
                    "description": f"Fetches {URL_WIKI}",
                    "input_schema": {"type": "object"},
                }
            ],
        }
        transformed, new_mappings = transform_request_body(body, pattern)

        # Verify URLs are gone from the transformed body
        transformed_str = json.dumps(transformed)
        assert URL_WIKI not in transformed_str
        assert URL_JIRA not in transformed_str

        # Restore using the mappings produced by transform
        restored = restore_response_body(transformed, new_mappings)
        restored_str = json.dumps(restored)
        assert URL_WIKI in restored_str
        assert URL_JIRA in restored_str

        # Verify structural equality of restored vs original
        assert restored["system"] == body["system"]
        assert restored["messages"][0]["content"] == body["messages"][0]["content"]
        assert (
            restored["messages"][1]["content"][0]["text"]
            == body["messages"][1]["content"][0]["text"]
        )
        assert restored["tools"][0]["description"] == body["tools"][0]["description"]

    def test_streaming_round_trip(self, pattern, mappings):
        """Simulate full streaming: content_block_start -> deltas -> stop."""
        # Transform a text that has a URL
        original_text = f"Check {URL_WIKI} for docs and {URL_JIRA} for tickets."
        from main import transform_text

        transformed_text, new_mappings = transform_text(original_text, pattern)

        # Simulate streaming the transformed text in small chunks
        buffers: dict[int, StreamBuffer] = {}

        # Start block
        start_events = handle_sse_event(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
            buffers,
            new_mappings,
        )
        assert len(start_events) == 1

        # Stream chunks of 10 chars
        collected_text = []
        chunk_size = 10
        for i in range(0, len(transformed_text), chunk_size):
            chunk = transformed_text[i : i + chunk_size]
            events = handle_sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": chunk},
                },
                buffers,
                new_mappings,
            )
            for _, ev_data in events:
                collected_text.append(ev_data["delta"]["text"])

        # Stop block (flushes remaining buffer)
        stop_events = handle_sse_event(
            "content_block_stop",
            {"type": "content_block_stop", "index": 0},
            buffers,
            new_mappings,
        )
        for ev_type, ev_data in stop_events:
            if ev_type == "content_block_delta":
                collected_text.append(ev_data["delta"]["text"])

        full_text = "".join(collected_text)
        assert URL_WIKI in full_text
        assert URL_JIRA in full_text
        assert PLACEHOLDER_WIKI not in full_text
        assert PLACEHOLDER_JIRA not in full_text
        assert full_text == original_text

    def test_tool_use_streaming_round_trip(self, pattern, mappings):
        """Simulate tool_use block streaming: accumulate JSON, restore on stop."""
        tool_input = {"url": URL_WIKI, "query": f"search {URL_JIRA}"}
        transformed_input, new_mappings = deep_walk_transform(tool_input, pattern)
        json_str = json.dumps(transformed_input)

        buffers: dict[int, StreamBuffer] = {}

        # Start tool_use block
        handle_sse_event(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Fetch",
                    "input": {},
                },
            },
            buffers,
            new_mappings,
        )

        # Stream JSON in fragments
        for i in range(0, len(json_str), 15):
            chunk = json_str[i : i + 15]
            events = handle_sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": chunk,
                    },
                },
                buffers,
                new_mappings,
            )
            # input_json_delta should never emit
            assert events == []

        # Stop block: should emit restored JSON
        stop_events = handle_sse_event(
            "content_block_stop",
            {"type": "content_block_stop", "index": 0},
            buffers,
            new_mappings,
        )

        assert len(stop_events) == 2
        json_event = stop_events[0]
        assert json_event[0] == "content_block_delta"
        restored = json.loads(json_event[1]["delta"]["partial_json"])
        assert restored["url"] == URL_WIKI
        assert URL_JIRA in restored["query"]
        assert stop_events[1][0] == "content_block_stop"


# ===================================================================
# PARTIAL_PLACEHOLDER_RE edge cases
# ===================================================================
class TestPartialPlaceholderRegex:
    def test_matches_opening_bracket(self):
        assert PARTIAL_PLACEHOLDER_RE.search("text [")

    def test_matches_partial_prefix(self):
        assert PARTIAL_PLACEHOLDER_RE.search("text [InternalLink_wiki")

    def test_matches_partial_hash(self):
        assert PARTIAL_PLACEHOLDER_RE.search("text [InternalLink_wiki_3e5f")

    def test_no_match_closed_bracket(self):
        # A closed bracket is not a partial
        m = PARTIAL_PLACEHOLDER_RE.search("text [InternalLink_wiki_3e5f8279]")
        assert m is None

    def test_no_match_no_bracket(self):
        assert PARTIAL_PLACEHOLDER_RE.search("plain text") is None

    def test_match_only_at_end(self):
        m = PARTIAL_PLACEHOLDER_RE.search("before [foo] after [bar")
        assert m is not None
        assert m.group() == "[bar"
