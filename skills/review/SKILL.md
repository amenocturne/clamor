---
name: review
description: Browser-based review and annotation UI. Review mode shows committed git changes for code review. Annotation mode opens any text file (lyrics, notes, prose, configs) for line-level commenting — use when the user wants to comment on, mark up, highlight, or react to specific lines in a file. Triggers on "review this", "let me review", "/review", "show me what changed", "annotate this", "comment on these lyrics", "let me mark up this file".
author: amenocturne
---

# Code Review & Text Annotation

Launch a local browser-based UI for reviewing committed git changes or annotating any text file. The browser tab auto-closes on submit.

## Modes

### Review Mode (default)

For reviewing committed git changes with inline comments.

```bash
just -f <skill-path>/justfile launch --repo "$(pwd)" --range HEAD~N..HEAD --message "Brief description"
```

### Text Annotation Mode

For annotating text files (lyrics, notes, prose) with line-level comments. Accepts multiple files and directories.

```bash
just -f <skill-path>/justfile launch --mode text --file "/path/to/file.txt" --message "Optional description"
just -f <skill-path>/justfile launch --mode text --file "/path/to/dir/" --file "/other/file.txt"
```

**CRITICAL: Use `run_in_background` parameter** when launching the server. This lets you receive a task notification when the user finishes.

## Flags

| Flag         | Required          | Default                     | Description              |
| ------------ | ----------------- | --------------------------- | ------------------------ |
| `--mode`     | no                | `review`                    | `review` or `text`       |
| `--repo`     | yes (review mode) | —                           | Repository path          |
| `--range`    | yes (review mode) | —                           | Git revision range       |
| `--file`     | yes (text mode)   | —                           | File or directory path (repeatable) |
| `--message`  | no                | —                           | Descriptive summary of changes for the reviewer. Must explain what changed and why — never just "Fix" or a one-word label. Include affected areas and what to check. |
| `--project`  | no                | filename (text) / — (review)| Project name (shown in header) |
| `--save-dir` | no                | `~/.claude/reviews/<repo>/` (review) or `~/.claude/annotations/` (text) | Where to save output |
| `--port`     | no                | `0` (auto)                  | Port (0 = auto-select)   |

## After Launching

1. Read the server output to get the URL (wait a moment for startup)
2. Tell the user the review URL
3. **STOP. Do not read the output file yet.** The user has not submitted.
4. Wait for the background task notification — it means the server exited because the user submitted.
5. Read the task output file — look for a line starting with `saved: ` which contains the full path to the review file
6. Read that file and act on the comments

## Important

- **Review mode:** Always commit before requesting review — only committed changes can be reviewed
- The server exits after submit — one review per invocation
- The browser tab auto-closes on submit
- **Do NOT try to find/read the output file before the task notification arrives**
