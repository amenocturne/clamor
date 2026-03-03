---
name: dp-gitlab
description: Interact with GitLab via the dp CLI. Use when user mentions merge requests, MRs, pipelines, or asks about GitLab resources. Triggers on "gitlab", "merge request", "MR", "show MRs", "list MRs", "pipeline status", "gitlab repo".
author: amenocturne
---

# dp GitLab

Interact with GitLab using the internal `dp` (dev platform) CLI.

## Defaults

| Parameter | Default |
|-----------|---------|
| Tenant (`-t`) | `crit-autoloans` |
| Repo (`-r`) | `autobroker` |

Apply these defaults unless the user specifies otherwise.

## Self-Discovery

Always run help commands to discover available subcommands and flags before executing:

```bash
dp gitlab --help
dp gitlab <subcommand> --help
```

## Common Commands

**List merge requests:**
```bash
dp gitlab merge-requests -t crit-autoloans -r autobroker
```

**With additional flags** — discover via:
```bash
dp gitlab merge-requests --help
```

## Authentication

If the command returns an auth error, the user needs to run:

```bash
dp auth login
```

Ask the user to run it in another terminal, then retry.