# Code Review

Launch a local browser-based review UI for committed git changes. The server blocks until the reviewer submits, then prints structured markdown to stdout.

## When to Use

- After making commits that warrant human review
- Before merging significant changes
- When you want feedback on implementation approach

## Usage

Always commit changes first, then invoke:

```bash
bun run <skill-path>/src/server.ts -- --repo "$(pwd)" --range HEAD~N..HEAD --message "Brief description of changes"
```

### Flags

| Flag         | Required | Default             | Description              |
| ------------ | -------- | ------------------- | ------------------------ |
| `--repo`     | yes      | —                   | Repository path          |
| `--range`    | yes      | —                   | Git revision range       |
| `--message`  | no       | —                   | Description of changes   |
| `--save-dir` | no       | `.reviews/` in repo | Where to save reviews    |
| `--port`     | no       | `0` (auto)          | Port (0 = auto-select)  |

## Output

The command blocks until the reviewer submits. On completion, structured markdown is printed to stdout. Read and act on the review feedback — fix issues marked as `[fix]`, consider `[suggestion]` items, and respond to `[question]` items.

## Important

- Always commit before requesting review — only committed changes can be reviewed
- The server exits after submit — one review per invocation
- Review is also saved to `.reviews/` directory in the repo
