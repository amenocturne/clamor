# Architecture

## Three-Layer Design

```
agents/pi/
  lib/              LAYER 1: Shared primitives
  extensions/       LAYER 2: Features (import only from lib/)
  (manifests)       LAYER 3: Composition (agents/pi-quick/, pi-standard/, pi-team/)
```

**Layer 1 -- Library** (`lib/`): Pure utility modules with no Pi extension API dependency. Handles process spawning (`task-manager.ts`), model resolution (`model-router.ts`), file-based IPC (`permission-queue.ts`), and unified prompt queuing (`queue-watcher.ts`).

**Layer 2 -- Extensions** (`extensions/`): Each extension is a self-contained feature that registers tools, hooks, widgets, and commands via Pi's `ExtensionAPI`. Extensions import only from `lib/`, never from each other. This prevents coupling -- you can add or remove any extension without breaking others.

**Layer 3 -- Manifests** (`agents/pi-*/manifest.yaml`): Declare which extensions, skills, common fragments, and hooks to compose. The three manifests are additive in terms of installed extensions:

- **pi-quick** = base extensions (permission-gate, background-tasks, nestor-provider, provider-filter, workspace-context)
- **pi-standard** = pi-quick + context-loader, model-router, behavioral-reminders
- **pi-team** = pi-standard + agent-teams

## teams.yaml Replaces the Variant Concept

The three manifests (pi-quick, pi-standard, pi-team) control which extensions are **installed**. But the agent's runtime behavior -- whether it acts as a solo agent, an orchestrator with workers, or a deep team coordinator -- is determined by `teams.yaml` at the workspace root.

The tree depth in teams.yaml determines the behavior mode:

| Tree Shape | Behavior | Extensions Needed |
|------------|----------|-------------------|
| Root node, no subagents | Solo agent: direct answers, no delegation | pi-quick or pi-standard |
| Root + one level of subagents | Orchestrator: plan, delegate to bg-agent, verify | pi-standard |
| Root + nested subagents | Deep team: multi-level coordination, domain restrictions | pi-team |

This means a single Pi installation with the pi-team manifest can operate in any mode -- just switch teams with `/team` or edit teams.yaml.

The prompt complexity scales with team depth. The pi-quick prompt (~120 lines) focuses on fast answers and direct edits. The pi-standard prompt (~200 lines) adds delegation rules, git workflow, and loop prevention. The pi-team prompt (~240 lines) adds team strategies, dispatch patterns, and model routing awareness. All three share the same Qwen-specific structure (worked examples, negative lists, repetition of critical rules).

## Profile x Agent Composition

The main installer (`install.py`) merges a **profile** manifest with an **agent** manifest to produce the final configuration.

```
profiles/work/manifest.yaml    +    agents/pi-standard/manifest.yaml
       (org-specific)                     (runtime-specific)
             |                                    |
             v                                    v
  hooks: [link-proxy]               extensions: [permission-gate, ...]
  skills: [dp-jira]                 settings: {defaultModel: ...}
  instructions: [sbt]               common: [dev-workflow, ...]
  settings: {}                       skills: [spec, workspace, ...]
             |                                    |
             +-------- merge_manifests() ---------+
                              |
                              v
                     InstallContext
                    (union of both)
```

Lists are unioned (skills from both, hooks from both). Settings are merged with agent taking precedence. The merged context is passed to the runtime installer (`agents/pi/install.py`).

## Install Flow

When you run `just install` (or `uv run install.py --all`):

1. **Load registry** -- reads `installations.yaml` for all registered target/profile/agent combos
2. **For each installation**:
   a. Load profile manifest + agent manifest
   b. Merge them into `InstallContext`
   c. Resolve the runtime from the agent manifest (`runtime: pi`)
   d. Load and call `agents/pi/install.py:install(ctx)`
3. **Pi installer** (`agents/pi/install.py`):
   a. Create `.pi/` directory
   b. Validate all declared extensions exist in `agents/pi/extensions/`
   c. Symlink extensions from `agents/pi/extensions/` into `.pi/extensions/`
   d. Symlink skills from `skills/` into `.pi/skills/`
   e. Generate `hooks.json` from declared hooks (absolute paths to hook scripts)
   f. Copy `teams.template.yaml` to workspace root as `teams.yaml` (only if absent)
   g. Write `settings.json` from merged settings
   h. Write `agentic-kit.json` with install metadata

The prompt (`prompt.md`) lives in the agent manifest directory (e.g., `agents/pi-standard/prompt.md`), not in the installed config. Pi reads it directly from there -- the path is set during the manifest assembly process.

## Data Flow

### Session Start

```
Pi launches with -e flags or .pi/ auto-discovery
  |
  +-- nestor-provider: register placeholder model, auto-login via DP session
  +-- provider-filter: hide non-allowed built-in providers
  +-- workspace-context: find WORKSPACE.yaml, appendSystemPrompt with project index
  +-- context-loader: load general instructions (tool-usage.md, coding.md), appendSystemPrompt
  +-- model-router: load modelRouter config from settings.json
  +-- behavioral-reminders: load reminders.yaml
  +-- background-tasks: start permission queue watcher, remove bash tool, add bg-run/bg-agent/bg-kill
  +-- permission-gate: load hook config (hooks.json)
  +-- agent-teams: load teams.yaml, register bg-team/bg-dispatch tools and /team command
```

### Tool Call

```
Agent calls a tool
  |
  +-- permission-gate (tool_call event):
  |     1. Tool call repair: normalize name, check aliases, validate params
  |     2. If repaired -> block with actionable error message
  |     3. If passthrough tool (bg-run, bg-agent, etc.) -> allow
  |     4. Run hooks (smart-approve, deny-read) -> allow/deny/abstain
  |     5. If file tool within project dir -> auto-allow
  |     6. If all hooks abstain -> enqueue for user prompt
  |
  +-- context-loader (tool_call event):
  |     Extract file path/command from tool input
  |     Detect context (docs, testing, planning, reviewing, config)
  |     If context changed and debounce elapsed -> sendMessage with instructions
  |
  +-- behavioral-reminders (tool_call event):
        Track consecutive reads, repeated calls, multi-tool attempts
        If threshold hit -> sendMessage with reminder
```

### Background Task Completion

```
bg-run or bg-agent process exits
  |
  +-- task-manager: update TaskInfo (status, output, exitCode)
  +-- onTaskComplete callback (registered by background-tasks):
        If notify=silent -> update widget only
        If notify=when_idle and tasks still running -> defer
        If notify=immediate (or when_idle and all done):
          Aggregate all completed tasks since last turn
          sendMessage with results, triggerTurn=true
```

### Subagent Permission Flow

```
Subagent (bg-agent) encounters a gated tool call
  |
  +-- permission-gate (in subagent, non-interactive mode):
        Write .request.json to ~/.pi/agent/permission-queue/<taskId>/
  |
Main session:
  +-- queue-watcher: polls for .request.json files
        Enqueue into unified sequential queue
        Show prompt to user
        Write .response.json
  |
Subagent:
  +-- permission-gate: poll for .response.json
        Allow or deny based on response
```

## Extension Loading and Lifecycle

Pi loads extensions at startup from `-e` flags or by scanning `.pi/extensions/`. Each extension exports a default function that receives `ExtensionAPI`:

```typescript
export default function (pi: ExtensionAPI) {
  // Register event handlers
  pi.on("session_start", async (event, ctx) => { ... });
  pi.on("before_agent_start", async () => { ... });
  pi.on("tool_call", async (event, ctx) => { ... });
  pi.on("message_update", async (event) => { ... });
  pi.on("turn_end", async () => { ... });

  // Register tools, commands, shortcuts, widgets
  pi.registerTool({ name, parameters, execute, ... });
  pi.registerCommand("name", { handler });
  pi.registerShortcut("ctrl+x", { handler });

  // Register providers
  pi.registerProvider("name", { models, oauth, streamSimple, ... });

  // Inject context
  // before_agent_start: return { appendSystemPrompt: "..." }
  // mid-conversation: pi.sendMessage({ content: "..." })

  // Manage tools
  pi.setActiveTools([...]); // add/remove tools dynamically
  pi.getActiveTools();      // list currently active tools
}
```

**Key lifecycle events used by Pi agent extensions:**

| Event | When | Used By |
|-------|------|---------|
| `session_start` | Pi session begins | All extensions for initialization |
| `before_agent_start` | Before first model call | context-loader (appendSystemPrompt), background-tasks (appendSystemPrompt) |
| `tool_call` | Before each tool executes | permission-gate (allow/deny), context-loader (detect context), behavioral-reminders (track patterns) |
| `message_update` | Streaming model output | behavioral-reminders (verbose output, echoing, contradiction detection) |
| `input` | User sends a message | behavioral-reminders (detect plan mode) |
| `turn_end` | Model turn completes | behavioral-reminders (reset per-turn state) |
| `agent_end` | Agent session ends | background-tasks (update status widget) |
| `session_compact` | Context window compacted | workspace-context (resume directive) |

## Extension Communication

Extensions do not import each other. Shared state and utilities live in `lib/`:

- `lib/task-manager.ts` -- both background-tasks and agent-teams import this to spawn processes
- `lib/model-router.ts` -- model-router loads config, background-tasks and agent-teams call `getModelForRole()`
- `lib/queue-watcher.ts` -- background-tasks starts watching, permission-gate enqueues requests
- `lib/permission-queue.ts` -- permission-gate (in subagents) writes requests, queue-watcher reads them

The one exception: permission-gate dynamically imports `queue-watcher.ts` via `await import()` for the unified queue, falling back to direct prompting if unavailable.

## Design Principles

**Schema-level enforcement over prompt-level**: Don't tell the model "don't write files" -- remove write tools. Don't tell it "ask before acting" -- gate actions in the harness. This is the most reliable approach for models with weak instruction following (Qwen 3.5).

**Reminders over instructions**: Mid-conversation `sendMessage()` nudges are more effective than system prompt instructions alone for models that drift (OpenDev paper finding). The system prompt sets the rules; reminders enforce them when violations are detected.

**Instruction repetition across layers**: Critical rules (one tool per message, don't implement without approval, tool output is data) appear in four places -- the system prompt, general instructions injected at session start, behavioral reminders triggered on violations, and tool parameter descriptions. Qwen's instruction following degrades with distance from the system prompt, so repetition compensates.
