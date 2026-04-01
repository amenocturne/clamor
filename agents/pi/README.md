# Pi Agent

The Pi agent runtime for agentic-kit. Turns [Pi](https://pi.dev/) into a configurable coding harness with permission gating, background task management, multi-agent teams, behavioral reminders, and model routing -- built as composable TypeScript extensions.

The core problem: open-source models (Qwen 3.5, GPT-OSS) ignore explicit instructions, loop on tool calls, and follow directives found in file contents. The Pi agent compensates with schema-level enforcement (removing tools, gating permissions), mid-conversation reminders (sendMessage nudges), and Qwen-specific prompt engineering (worked examples, repetition layering, negative lists).

## Quick Start

```bash
# Install with a profile
uv run install.py --profile work --agents pi-standard --target /path/to/workspace

# Or install all registered targets
just install

# Run Pi with the installed config
cd /path/to/workspace
pi  # auto-discovers .pi/ config
```

The installer creates a `.pi/` directory at the target with symlinked extensions, merged settings, and the system prompt. It also creates `teams.yaml` at the workspace root if absent -- this file controls how the agent behaves.

## Configuration Model: teams.yaml

The agent's behavior is determined by `teams.yaml` at the workspace root. The tree depth in your team configuration determines the mode:

| Configuration | Behavior | Equivalent to |
|---------------|----------|---------------|
| **Solo agent** -- no subagents | Fast answers, direct edits, no delegation | Lightweight single-agent mode |
| **Orchestrator + workers** -- one level of subagents | Plan, delegate, verify -- full dev workflow | Standard development mode |
| **Deep teams** -- subagents with their own subagents | Multi-team coordination, domain-restricted specialists | Team orchestration mode |

```yaml
# Solo -- just you and the model
solo:
  prompt: "You are a senior engineer. Be concise."
  role: orchestrator

# Orchestrator + workers
plan-build:
  prompt: "You plan and coordinate. Delegate implementation."
  role: orchestrator
  subagents:
    builder:
      prompt: "You implement code changes as instructed."
      role: worker

# Deep team -- subagents have subagents
engineering:
  prompt: "You are the engineering lead. Break tasks into subtasks."
  role: orchestrator
  subagents:
    backend:
      prompt: "You implement API endpoints and services."
      role: worker
      subagents:
        database:
          prompt: "You handle migrations and queries."
          role: worker
```

Switch teams at runtime with `/team`. See [docs/teams.md](docs/teams.md) for the full configuration reference.

## Agent Manifests

Three manifests exist for install-time extension selection. They control which extensions are installed, but the runtime behavior (solo vs. orchestrator vs. deep team) is controlled by `teams.yaml`:

| Manifest | Extensions | Use When |
|----------|-----------|----------|
| **pi-quick** | permission-gate, background-tasks, nestor-provider, provider-filter, workspace-context | You want minimal overhead, no context tracking |
| **pi-standard** | + context-loader, model-router, behavioral-reminders | Full development with context awareness and model routing |
| **pi-team** | + agent-teams | You need bg-team strategies and bg-dispatch for named teams |

Each manifest is in `agents/pi-<name>/manifest.yaml`. They share the same installer, library, and extension code.

## Extensions

| Extension | Purpose |
|-----------|---------|
| [permission-gate](docs/extensions.md#permission-gate) | Intercept tool calls, run hooks, gate permissions, repair hallucinated tool names |
| [background-tasks](docs/extensions.md#background-tasks) | `bg-run` and `bg-agent` tools with live widget, notify modes, auto-result delivery |
| [nestor-provider](docs/extensions.md#nestor-provider) | Tinkoff internal LLM API via DP auth, OpenAI-compatible streaming, think-tag parsing |
| [provider-filter](docs/extensions.md#provider-filter) | Hide unwanted built-in providers from the model picker |
| [workspace-context](docs/extensions.md#workspace-context) | Inject WORKSPACE.yaml project index into the system prompt |
| [model-router](docs/extensions.md#model-router) | Route agent roles (orchestrator, worker, reviewer) to different models |
| [behavioral-reminders](docs/extensions.md#behavioral-reminders) | Mid-conversation nudges when the model drifts (exploration spirals, loops, verbosity) |
| [context-loader](docs/extensions.md#context-loader) | Detect work context from tool calls, inject relevant instruction files |
| [agent-teams](docs/extensions.md#agent-teams) | Multi-agent strategies (best-of-n, debate, ensemble) and named team trees |

## Documentation

- [Architecture](docs/architecture.md) -- three-layer design, teams.yaml as the behavior model, install and data flow
- [Teams](docs/teams.md) -- teams.yaml format, solo/orchestrator/deep-team configs, strategies, dispatch
- [Extensions](docs/extensions.md) -- all 9 extensions with config and implementation details
- [System Prompts](docs/system-prompts.md) -- prompt structure, Qwen steering techniques, instruction layering
- [Behavioral Reminders](docs/behavioral-reminders.md) -- all 8 reminders, detection logic, tuning
- [Model Routing](docs/model-routing.md) -- role-based routing, providers, model capabilities

## Configuration

All settings live in `.pi/settings.json`, written by the installer from merged profile + agent manifests:

```json
{
  "defaultProvider": "nestor",
  "defaultModel": "tgpt/qwen3-next-80b-a3b-instruct",
  "allowedProviders": ["nestor"],
  "defaultThinkingLevel": "medium",
  "modelRouter": {
    "orchestrator": "tgpt/qwen3-next-80b-a3b-instruct",
    "worker": "tgpt/qwen35-397b-a17b-fp8",
    "reviewer": "tgpt/qwen3-next-80b-a3b-instruct"
  }
}
```

| Field | Used By | Purpose |
|-------|---------|---------|
| `defaultProvider` | Pi core | Provider selected at startup |
| `defaultModel` | nestor-provider | Model ID for the placeholder registration |
| `allowedProviders` | provider-filter | Which providers remain visible |
| `defaultThinkingLevel` | Pi core | Thinking level (off, low, medium, high) |
| `modelRouter` | model-router | Role-to-model mappings |

## Project Structure

```
agents/pi/
  lib/                        # Shared primitives (imported by extensions)
    model-router.ts           # Role -> model resolution
    task-manager.ts           # Process spawning and lifecycle
    permission-queue.ts       # File-based IPC for subagent permissions
    queue-watcher.ts          # Unified sequential permission queue
  extensions/                 # 9 feature extensions
  instructions/               # 6 instruction files (injected by context-loader)
  teams.template.yaml         # Default teams.yaml copied to workspace root
  install.py                  # Runtime installer (called by main install.py)
  docs/                       # This documentation

agents/pi-quick/              # Minimal manifest + lightweight prompt
agents/pi-standard/           # Full development manifest + standard prompt
agents/pi-team/               # Team orchestration manifest + team prompt
```
