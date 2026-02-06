# Save Conversation Hook

Automatically saves conversation transcripts on session end.

## What It Does

1. Copies raw JSONL transcript to `logs/YYYY-MM-DD/<session_id>.json`
2. Renames pending summaries (`_*.md` → `HHMMSS *.md`)
3. Formats markdown files with Prettier (if available)
4. Commits changes to git

## Setup

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "{hook_dir}/hook.py",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

## Environment

- `NO_LOG=1` — Disable logging for this session

## Workflow

The hook works with the knowledge-base saving convention:

1. During conversation, create summaries as `logs/YYYY-MM-DD/_Topic.md`
2. Use `{LOG_ID}` placeholder for transcript links
3. On Stop, hook renames files and replaces placeholders
