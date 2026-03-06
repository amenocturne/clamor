---
name: review
description: Browser-based code review UI for committed changes. Use after significant commits to get human feedback before proceeding. Triggers on "review this", "let me review", "/review", "show me what changed".
author: amenocturne
---

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

**CRITICAL: Use `run_in_background` parameter** when launching the server. This lets you receive a task notification when the user finishes reviewing.

### Flags

| Flag         | Required | Default             | Description              |
| ------------ | -------- | ------------------- | ------------------------ |
| `--repo`     | yes      | —                   | Repository path          |
| `--range`    | yes      | —                   | Git revision range       |
| `--message`  | no       | —                   | Description of changes   |
| `--project`  | no       | —                   | Project name (shown in header) |
| `--save-dir` | no       | `~/.claude/reviews/<repo>/` | Where to save reviews    |
| `--port`     | no       | `0` (auto)          | Port (0 = auto-select)  |

## After Launching

1. Read the server output to get the URL (wait a moment for startup)
2. Tell the user the review URL
3. **STOP. Do not read the review file yet.** The user has not submitted.
4. Wait for the background task notification — it means the server exited because the user submitted.
5. THEN read the latest `.md` file from `--save-dir` (default: `~/.claude/reviews/<repo>/`)
6. Act on the review comments

## Important

- Always commit before requesting review — only committed changes can be reviewed
- The server exits after submit — one review per invocation
- The browser tab auto-closes on submit
- Reviews saved to `~/.claude/reviews/<repo>/` (outside the repo)
- **Do NOT try to find/read the review file before the task notification arrives**
