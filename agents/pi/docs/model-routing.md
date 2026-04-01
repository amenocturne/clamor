# Model Routing

Role-based model routing assigns different LLMs to different agent roles. Configured in `settings.json`, resolved by `lib/model-router.ts`, consumed by background-tasks and agent-teams.

## Role Definitions

| Role | Used By | Optimized For |
|------|---------|---------------|
| `orchestrator` | Pi main session | Instruction following, planning, coordination |
| `lead` | agent-teams tree nodes with subagents | Delegation, synthesis |
| `worker` | bg-agent, team workers | Raw coding power, implementation |
| `reviewer` | agent-teams reviewer step | Evaluation, critique, synthesis |
| `default` | Fallback when role has no mapping | -- |

Roles are arbitrary strings. The four above are conventions. You can add `"security-expert": "some-model"` to the router config and use `role: security-expert` in teams.yaml.

## Configuration

In `.pi/settings.json` (written by the installer):

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

The `default` key is the fallback -- used when `getModelForRole()` is called with a role that has no explicit mapping:

```json
{
  "modelRouter": {
    "orchestrator": "tgpt/qwen3-next-80b-a3b-instruct",
    "default": "tgpt/qwen35-397b-a17b-fp8"
  }
}
```

## How Routing Integrates

### bg-agent

When spawning a subagent, background-tasks imports `getModelForRole("worker")` from `lib/model-router.ts`:

```typescript
const { getModelForRole } = await import("../../lib/model-router.ts");
const workerModel = getModelForRole("worker");
model = workerModel || `${ctx.model.provider}/${ctx.model.id}`;
```

If the worker role has no mapping, falls back to the session's current model.

### bg-team (ad-hoc strategies)

Agent-teams resolves two models per strategy execution:

```typescript
const workerModel = await resolveModel("worker", ctx);
const reviewerModel = await resolveModel("reviewer", ctx);
```

Workers get the `worker` model. The reviewer step gets the `reviewer` model. If reviewer has no mapping, it falls back through `default`, then to the session model.

### bg-dispatch (named teams)

Each node in the team tree has a `role` field. When spawning that node as a subagent, agent-teams calls:

```typescript
const model = await resolveModel(agent.role, ctx);
```

This means a team tree can use different models at each level without any per-node model configuration -- the role handles it.

## Current Model Landscape

Available on the internal Nestor/Tinkoff GPU cluster:

| Model | Active Params | Strengths | Weaknesses | Typical Role |
|-------|--------------|-----------|------------|--------------|
| `tgpt/qwen35-397b-a17b-fp8` | 17B (MoE) | Raw coding/reasoning, 1M context | Poor instruction following (IFEval 82), overthinking loops | worker |
| `tgpt/gpt-oss-120b` | 120B | More predictable, better constraint compliance | Lower ceiling on all benchmarks | -- |
| `tgpt/qwen3-next-80b-a3b-instruct` | 3.9B (MoE) | Best IFEval (87.6), fastest inference (~346 tok/s), good tool calling (BFCL 70.3) | Weaker deep reasoning (GPQA 72.9) | orchestrator, reviewer |

**Routing rationale**: The orchestrator needs reliable instruction following (don't implement, delegate, follow the workflow). Qwen3-next-80b is best at this despite weaker reasoning. Workers need raw coding power for bounded tasks where instruction following matters less. Qwen 3.5 397B excels here.

## The Nestor Provider

The `nestor-provider` extension connects Pi to Tinkoff's internal LLM API. The API is OpenAI-compatible, so Pi's built-in OpenAI completions streaming works with a custom `Nestor-Token` header.

### Auth Flow

```
dp auth login (user runs in terminal)
      |
      v
dp auth print-token -> DP access token
      |
      v
POST /api/v2/token (exchange for JWT)
      |
      v
Nestor JWT (used in all API calls as Nestor-Token header)
```

The `dp` binary manages the DevPlatform auth session. It stores tokens in `~/.nessy/dp_v13.4.2/` or its own default workdir. The extension finds it at `/usr/local/bin/dp` or `~/.nessy/dp_v13.4.2/dp`.

On session start, the extension silently tries the existing DP session. If it works, no `/login` is needed. If not, the user runs `/login nestor` which prompts them to run `dp auth login` in another terminal.

### Model Discovery

After auth, the extension fetches models from `GET /api/v1/cli/models`. The response doesn't include context window or max token limits, so these are inferred from model name patterns:

- `qwen35` -> 1M context, 16K max tokens
- `qwen3` -> 128K context, 8K max tokens
- `gpt-oss` -> 128K context, 4K max tokens

### API Compatibility

The Nestor API is OpenAI-compatible with these caveats:

- `parallel_tool_calls: false` is set on every request with tools. Part of the OpenAI chat completions spec, so it should work even though other params are ignored.
- `supportsDeveloperRole: false` -- the API doesn't support the `developer` message role
- Thinking output comes as `<think>...</think>` tags in content, not as `reasoning_content`. The extension has a streaming interceptor that parses these tags into proper Pi thinking events.

## parallel_tool_calls: false

Set by nestor-provider on every completion request that includes tools:

```typescript
onPayload: (payload) => {
  if (p.tools && p.tools.length > 0) {
    p.parallel_tool_calls = false;
  }
  return p;
},
```

This is schema-level enforcement of the "one tool per message" rule. It tells the API to constrain the model to return at most one tool call per response.

Whether the Nestor API actually respects this parameter is uncertain -- it silently ignores many OpenAI parameters. The behavioral reminder `multi_tool_attempt` serves as a fallback detector (see [behavioral-reminders.md](behavioral-reminders.md)).

## Sampling Parameters

**The Nestor API silently ignores all sampling parameters.** Tested 2026-04-01: `temperature=2.0` produces identical output to `temperature=0.0`. Bogus parameters also pass silently -- the API is fully permissive and drops unknown fields.

This means recommended Qwen sampling params are not available:
- `presence_penalty=1.5` (targets overthinking loops) -- **not available**
- `temperature=0.6, top_p=0.95, top_k=20` (recommended for coding) -- **not available**

Compensated by:
- Behavioral reminders (`self_contradiction` detects overthinking loops)
- Prompt-level directives ("pick an approach and commit to it")
- The one-tool-per-message rule (reduces opportunity for spiraling)

If the Nestor AI team adds sampling param support later, add them to the `onPayload` callback in `nestor-provider/index.ts`.
