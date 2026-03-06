# Code Review

Launch a local browser-based review UI for committed git changes. The browser tab auto-closes on submit.

## When to Use

- After making commits that warrant human review
- Before merging significant changes
- When you want feedback on implementation approach

## Usage

Always commit changes first, then invoke:

```bash
bun run <skill-path>/src/server.ts -- --repo "$(pwd)" --range HEAD~N..HEAD --message "Brief description of changes" &
```

Run with `&` so the server lives independently with no timeout. The user may be away when you start the review — the server must survive until they return and submit.

### Flags

| Flag         | Required | Default             | Description              |
| ------------ | -------- | ------------------- | ------------------------ |
| `--repo`     | yes      | —                   | Repository path          |
| `--range`    | yes      | —                   | Git revision range       |
| `--message`  | no       | —                   | Description of changes   |
| `--save-dir` | no       | `~/.claude/reviews/<repo>/` | Where to save reviews    |
| `--port`     | no       | `0` (auto)          | Port (0 = auto-select)  |

## After Submission

The server exits after the reviewer submits. When you see the process terminate:

1. Read the latest file from the `--save-dir` (default: `~/.claude/reviews/<repo>/`)
2. Act on the review feedback:
   - `[fix]` — must fix before proceeding
   - `[suggestion]` — consider and apply if reasonable
   - `[question]` — respond or clarify in the code

## Important

- Always commit before requesting review — only committed changes can be reviewed
- The server exits after submit — one review per invocation
- The browser tab auto-closes on submit
- Reviews saved to `~/.claude/reviews/<repo>/` (outside the repo)
