# Link Proxy

URL masking hook for Claude Code. Transforms internal URLs to placeholders before Claude sees them, and restores them when writing files.

## Use Case

When working in environments where an LLM proxy masks URLs in API traffic, but files on disk contain real URLs. This hook ensures Claude can read/edit files without corrupting URLs.

## Setup

1. Copy `domains.txt.template` to `domains.txt`
2. Add your internal domains (one per line)
3. Configure hooks in your project's `.claude/settings.json`

## Configuration

Add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Write|Edit",
        "hooks": [
          {
            "type": "command",
            "command": "path/to/link-proxy/hook.sh pre-tool-use",
            "timeout": 10
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit",
        "hooks": [
          {
            "type": "command",
            "command": "path/to/link-proxy/hook.sh post-tool-use",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "path/to/link-proxy/hook.sh stop",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## How It Works

Uses **in-place file transformation** to avoid Claude Code's file tracking issues:

1. User configures internal domains in `domains.txt`
2. On `PreToolUse` (Read): Transform URLs to placeholders **in the original file**
3. Claude reads the file normally (file is marked as "read")
4. On `PreToolUse` (Edit): Restore URLs in `new_string` if it contains placeholders
5. On `PostToolUse` (Edit): Re-transform any new URLs introduced by the edit
6. On `PreToolUse` (Write): Restore URLs in content before writing
7. On `Stop`: Restore all transformed files to original state (URLs restored)

## Data

- `data/mappings.json` - Global URL→hash mappings (shared across sessions)
- `data/sessions/{id}.json` - Per-session list of transformed files

## TODO

- **Phase 3**: Add PHONE detector (simplified regex, no external deps) and DATE detector (19 Russian date patterns from anon)
- **Phase 4**: Add NAME/SURNAME/PATRONYMIC and ADDRESS detection via `natasha` library (needs dep added to pyproject.toml)
