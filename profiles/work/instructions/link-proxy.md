## Link Proxy

A local proxy intercepts API traffic and transforms internal URLs to/from
placeholders. It starts automatically on session start.

**What you need to know:**
- Internal URLs work transparently — no special handling needed
- If you see connection errors, the proxy may not be running.
  Check: `curl http://127.0.0.1:18923/health`
  Start: `uv run hooks/link-proxy/proxy.py`
