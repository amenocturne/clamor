---
name: dp-jira
description: Fetch Jira issue details via the dp CLI. Use when user mentions a Jira issue key (e.g. ITAL-1234), asks to look up a ticket, check issue status, or get task description. Triggers on Jira issue keys, "check ticket", "look up issue", "what does ITAL-* say".
author: amenocturne
---

# dp Jira

Fetch Jira issues using the internal `dp` (dev platform) CLI.

## Command

```bash
dp jira issue --key ITAL-1234
```

Returns JSON. Pipe through `jq` to extract what you need.

## Authentication

If the command returns an error, the user is not authenticated. They need to run:

```bash
dp auth login
```

This can be run from any terminal — auth is synced globally. Ask the user to run it in another terminal, then retry the command.

## JSON Structure

The response is a paginated list. The issue is at `.issues[0]`, with metadata at the top level and all issue fields under `.issues[0].fields`. Some fields are nested objects:

| Path | Description |
|------|-------------|
| `.issues[0].key` | Issue key (e.g. `ITAL-1234`) |
| `.issues[0].fields.summary` | Issue title / headline |
| `.issues[0].fields.description` | Full issue description (plain text, may contain Jira markup) |
| `.issues[0].fields.status.name` | Current workflow status (e.g. `In Progress`, `Done`, `To Do`) |
| `.issues[0].fields.issuetype.name` | Issue type (e.g. `Story`, `Bug`, `Task`, `Documentation`) |
| `.issues[0].fields.priority.name` | Priority level (e.g. `High`, `Normal`, `Low`) |
| `.issues[0].fields.assignee.displayName` | Assigned user display name |
| `.issues[0].fields.reporter.displayName` | Reporter display name |
| `.issues[0].fields.created` | Creation timestamp (ISO 8601) |
| `.issues[0].fields.updated` | Last updated timestamp (ISO 8601) |
| `.issues[0].fields.labels` | Array of label strings |
| `.issues[0].fields.components[].name` | Component names |
| `.issues[0].fields.comment.comments` | Array of comment objects (`{ author: {displayName}, body, created }`) |

## Common jq Patterns

**Key context for working on a task** (most common):
```bash
dp jira issue --key ITAL-1234 | jq '.issues[0] | {key, summary: .fields.summary, description: .fields.description, status: .fields.status.name, issuetype: .fields.issuetype.name, priority: .fields.priority.name}'
```

**Title and description only:**
```bash
dp jira issue --key ITAL-1234 | jq '.issues[0].fields | {summary, description}'
```

**Just the description:**
```bash
dp jira issue --key ITAL-1234 | jq -r '.issues[0].fields.description'
```

**Status and assignee:**
```bash
dp jira issue --key ITAL-1234 | jq '.issues[0] | {summary: .fields.summary, status: .fields.status.name, assignee: .fields.assignee.displayName}'
```

**Latest comment:**
```bash
dp jira issue --key ITAL-1234 | jq '.issues[0].fields.comment.comments[-1] | {author: .author.displayName, body, created}'
```
