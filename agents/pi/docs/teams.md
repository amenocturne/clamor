# Teams

`teams.yaml` is the single configuration point that determines how the Pi agent behaves. It lives at the workspace root (next to `WORKSPACE.yaml`) and defines named teams of agents as hierarchical trees.

The tree depth controls the behavior mode. There are no separate "agent variants" to choose from at runtime -- you configure one file and switch teams with `/team`.

## Configuration Format

```yaml
teams:
  team-name:
    prompt: "System prompt text or path to .md file"
    role: orchestrator          # Model role (see Model Routing below)
    domain:                     # Optional: file path restrictions
      read: ["src/**"]          # Glob patterns the agent can read
      write: ["src/**"]         # Glob patterns the agent can write
    subagents:                  # Optional: child agents (recursive, unlimited depth)
      agent-name:
        prompt: "..."
        role: worker
        subagents: ...          # Subagents can have their own subagents
```

**Fields:**

| Field | Required | Description |
|-------|----------|-------------|
| `prompt` | Yes | System prompt. Inline string or relative path to a `.md` file. |
| `role` | Yes | Model role for model-router: `orchestrator`, `lead`, `worker`, `reviewer`, or custom. |
| `domain.read` | No | Glob patterns the agent is allowed to read. Default: all files. |
| `domain.write` | No | Glob patterns the agent is allowed to write. Default: all files. |
| `subagents` | No | Named child agents. Recursive -- each subagent has the same schema. |

## Solo Agent

No subagents. The model handles everything directly. Best for quick questions, small edits, lookups.

```yaml
teams:
  solo:
    prompt: "You are a senior engineer. Be concise, follow instructions exactly."
    role: orchestrator
```

When dispatched via `bg-dispatch`, a solo agent just runs the task directly with no coordination overhead.

Prompt complexity is minimal -- no delegation rules, no team strategies, no dispatch patterns. The system prompt focuses on tool usage, output format, and constraint compliance.

## Orchestrator + Workers

One level of subagents. The root orchestrator plans and delegates; workers implement. This is the standard development workflow.

```yaml
teams:
  plan-build:
    prompt: "You plan and coordinate. Delegate all implementation to subagents."
    role: orchestrator
    subagents:
      builder:
        prompt: "You implement code changes as instructed. Be precise, minimal diffs."
        role: worker
      reviewer:
        prompt: "You review code for correctness, security, and style issues."
        role: reviewer
```

When dispatched:
1. All subagents receive the task in parallel
2. Each subagent works independently
3. The orchestrator receives all results and synthesizes a final output

The orchestrator's prompt should include delegation rules. The worker's prompt should focus on implementation. The reviewer's prompt should focus on evaluation. Model routing assigns different models to each role automatically.

## Deep Teams

Subagents have their own subagents. Use for complex projects where different domains need specialized agents.

```yaml
teams:
  engineering:
    prompt: "You are the engineering lead. Break tasks into clear subtasks and delegate."
    role: orchestrator
    subagents:
      frontend:
        prompt: "You implement UI components, pages, and client-side logic."
        role: worker
        domain:
          write: ["src/frontend/**", "src/components/**", "src/styles/**"]
      backend:
        prompt: "You implement API endpoints, services, and business logic."
        role: worker
        domain:
          write: ["src/backend/**", "src/api/**", "src/services/**"]
        subagents:
          database:
            prompt: "You handle database migrations, queries, and schema changes."
            role: worker
            domain:
              write: ["migrations/**", "src/db/**", "src/models/**"]
      testing:
        prompt: "You write and fix tests. Ensure coverage for changed code."
        role: worker
        domain:
          write: ["tests/**", "src/**/*.test.*", "src/**/*.spec.*"]
```

Domain restrictions (`domain.write`) are injected into each subagent's prompt as hard constraints. The agent is told it may ONLY write to matching paths.

The tree can go arbitrarily deep. The `backend` agent above has its own `database` subagent. When `backend` receives a task involving schema changes, it can delegate to `database`.

## Multi-Perspective Review

A common pattern: multiple reviewers with different focus areas, orchestrator synthesizes.

```yaml
teams:
  review:
    prompt: "You coordinate a multi-perspective code review."
    role: orchestrator
    subagents:
      correctness:
        prompt: "Review for logical errors, edge cases, and incorrect behavior."
        role: reviewer
      security:
        prompt: "Review for security vulnerabilities: injection, auth bypass, data exposure."
        role: reviewer
      architecture:
        prompt: "Review for architectural fit, abstractions, and maintainability."
        role: reviewer
```

## Using Teams

### /team Command

Select the active team for the session:

```
/team
> Select team
  solo
  plan-build (2 subagents)
  engineering (3 subagents)
  review (3 subagents)
```

The selected team is used by `bg-dispatch`.

### bg-dispatch Tool

Dispatch a task to the active team's tree:

```
bg-dispatch("Implement the user profile page with avatar upload")
```

The orchestrator (root node) spawns all its subagents in parallel, waits for results, then synthesizes. If no team is selected, lists available teams.

You can override the team per-call:

```
bg-dispatch("Review the auth changes", team: "review")
```

### bg-team Tool (Ad-hoc Strategies)

For one-off multi-agent patterns without teams.yaml configuration:

```
bg-team("Implement retry logic for the API client", strategy: "best-of-n", workers: 3)
bg-team("Review the auth middleware", strategy: "debate", rounds: 2)
bg-team("Implement the caching layer", strategy: "ensemble", workers: 4)
```

**Strategies:**

| Strategy | Flow | Use When |
|----------|------|----------|
| **best-of-n** | N workers solve independently, reviewer picks best | Design decisions, algorithm choices |
| **debate** | Propose, critique, revise, synthesize (N rounds) | Architecture decisions, security review, tricky bugs |
| **ensemble** | N workers solve from different angles (correctness, simplicity, performance, robustness), reviewer synthesizes | Critical code paths, complex algorithms |

## Prompt Paths

The `prompt` field accepts:
- **Inline string**: `prompt: "You are a senior engineer."` -- used directly as the system prompt
- **File path**: `prompt: prompts/backend.md` -- resolved relative to `teams.yaml` location, file contents used as the system prompt

File paths are useful for long prompts that would clutter teams.yaml.

## Model Routing

Each agent node's `role` field maps to a model via `modelRouter` in `settings.json`:

```json
{
  "modelRouter": {
    "orchestrator": "tgpt/qwen3-next-80b-a3b-instruct",
    "lead": "tgpt/qwen3-next-80b-a3b-instruct",
    "worker": "tgpt/qwen35-397b-a17b-fp8",
    "reviewer": "tgpt/qwen3-next-80b-a3b-instruct"
  }
}
```

This means orchestrators use the fast instruction-following model, workers use the powerful coding model, and reviewers use the balanced model. No need to specify models per-agent -- the role handles it.

Custom roles work too. If you add `role: security-expert` to a node and `"security-expert": "some-model"` to modelRouter, it resolves automatically.

## Execution Model

When `bg-dispatch` dispatches to a team:

1. The orchestrator node is identified as the root
2. All first-level subagents are spawned as Pi subprocesses in parallel
3. Each subagent receives: its prompt + the task + domain restrictions (if any) + list of its own subagents (if any)
4. Subagents with their own subagents can delegate further via bg-agent
5. When all subagents complete, the orchestrator receives all results
6. The orchestrator synthesizes a final output from all subagent results

If the root has no subagents (solo configuration), the task is run directly as a single agent.

## Extension Inheritance

Subagents spawned by bg-dispatch inherit extensions from the `.pi/extensions/` directory, excluding `background-tasks` (to prevent recursive spawning) and `agent-teams` (subagents don't need team management). This means subagents get permission-gate, nestor-provider, provider-filter, and other non-recursive extensions automatically.
