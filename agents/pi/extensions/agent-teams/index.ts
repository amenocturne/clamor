/**
 * Agent Teams — Pi Extension
 *
 * Two modes of multi-agent coordination:
 *
 * 1. Ad-hoc strategies (bg-team tool):
 *    best-of-n, debate, ensemble — quick multi-agent patterns without config.
 *
 * 2. Named teams from teams.yaml (bg-dispatch tool + /team command):
 *    Hierarchical agent trees where the orchestrator (root) delegates to
 *    subagents, which can have their own subagents, arbitrarily deep.
 *    Domain restrictions limit which files each agent can write.
 *
 * teams.yaml lives at the workspace root (next to WORKSPACE.yaml).
 */

import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";
import { existsSync, readFileSync, readdirSync } from "fs";
import { dirname, join, resolve } from "path";
import { parse } from "yaml";
import { spawnAgent, generateTaskId, type TaskInfo } from "../../lib/task-manager.ts";

// ── Types ───────────────────────────────────────────────────────────────

interface AgentNode {
  prompt: string;
  role: string;
  domain?: { read?: string[]; write?: string[] };
  subagents?: Record<string, AgentNode>;
}

interface TeamsConfig {
  teams: Record<string, AgentNode>;
}

// ── State ───────────────────────────────────────────────────────────────

let teamsConfig: TeamsConfig | null = null;
let activeTeamName: string | null = null;

// ── Config Loading ──────────────────────────────────────────────────────

function findTeamsYaml(): string | null {
  let dir = resolve(process.cwd());
  for (let i = 0; i < 5; i++) {
    const candidate = join(dir, "teams.yaml");
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function loadTeams(): TeamsConfig | null {
  const path = findTeamsYaml();
  if (!path) return null;
  try {
    const raw = readFileSync(path, "utf-8");
    const parsed = parse(raw);
    if (parsed?.teams && typeof parsed.teams === "object") return parsed as TeamsConfig;
    return null;
  } catch {
    return null;
  }
}

function resolvePrompt(prompt: string): string {
  // If prompt looks like a file path, try to read it
  if (prompt.endsWith(".md") && !prompt.includes("\n")) {
    const teamsPath = findTeamsYaml();
    if (teamsPath) {
      const fullPath = resolve(dirname(teamsPath), prompt);
      if (existsSync(fullPath)) {
        try { return readFileSync(fullPath, "utf-8"); } catch {}
      }
    }
  }
  return prompt;
}

// ── Model Resolution ────────────────────────────────────────────────────

async function resolveModel(role: string, ctx: ExtensionContext): Promise<string> {
  try {
    const { getModelForRole } = await import("../../lib/model-router.ts");
    const model = getModelForRole(role);
    if (model) return model;
  } catch {}
  return ctx.model ? `${ctx.model.provider}/${ctx.model.id}` : "";
}

// ── Extension Discovery ─────────────────────────────────────────────────

function getExtensionsForSubagent(): string[] {
  const extDir = join(process.cwd(), ".pi", "extensions");
  const selfNames = new Set(["background-tasks", "agent-teams"]);
  if (!existsSync(extDir)) return [];

  const paths: string[] = [];
  for (const entry of readdirSync(extDir)) {
    if (selfNames.has(entry)) continue;
    const full = resolve(extDir, entry);
    if (existsSync(join(full, "index.ts")) || existsSync(join(full, "package.json"))) {
      paths.push(full);
    }
  }
  return paths;
}

// ── Worker Spawning ─────────────────────────────────────────────────────

async function spawnWorker(task: string, model: string): Promise<TaskInfo> {
  const id = generateTaskId();
  return spawnAgent(id, task, model, process.cwd(), getExtensionsForSubagent(), "silent");
}

function waitForTask(info: TaskInfo): Promise<TaskInfo> {
  return new Promise((resolve) => {
    const check = setInterval(() => {
      if (info.status !== "running" && info.status !== "waiting") {
        clearInterval(check);
        resolve(info);
      }
    }, 500);
  });
}

function getResult(info: TaskInfo): string {
  if (info.type === "agent" && info.finalReport) return info.finalReport;
  return info.output || "(no output)";
}

// ── Ad-hoc Strategies ───────────────────────────────────────────────────

async function bestOfN(
  task: string, n: number, workerModel: string,
  reviewerModel: string, reviewerPrompt: string,
): Promise<string> {
  const workers: TaskInfo[] = [];
  for (let i = 0; i < n; i++) {
    workers.push(await spawnWorker(task, workerModel));
  }
  const results = await Promise.all(workers.map(waitForTask));
  const outputs = results.map((r, i) =>
    `## Worker ${i + 1} [${r.status}]\n\n${getResult(r)}`
  ).join("\n\n---\n\n");
  const reviewTask = `${reviewerPrompt}\n\n# Original Task\n${task}\n\n# Worker Outputs\n${outputs}`;
  const reviewer = await spawnWorker(reviewTask, reviewerModel);
  return getResult(await waitForTask(reviewer));
}

async function debate(
  task: string, rounds: number, workerModel: string,
  reviewerModel: string, reviewerPrompt: string,
): Promise<string> {
  let proposal = "";
  let critique = "";
  for (let r = 0; r < rounds; r++) {
    const propTask = r === 0 ? task : `${task}\n\n# Previous Critique\nAddress this and improve:\n${critique}`;
    proposal = getResult(await waitForTask(await spawnWorker(propTask, workerModel)));
    const critTask = `You are a critical reviewer. Find flaws and suggest improvements.\n\n# Original Task\n${task}\n\n# Proposed Solution\n${proposal}`;
    critique = getResult(await waitForTask(await spawnWorker(critTask, workerModel)));
  }
  const reviewTask = `${reviewerPrompt}\n\n# Original Task\n${task}\n\n# Final Proposal\n${proposal}\n\n# Final Critique\n${critique}`;
  return getResult(await waitForTask(await spawnWorker(reviewTask, reviewerModel)));
}

async function ensemble(
  task: string, n: number, workerModel: string,
  reviewerModel: string, reviewerPrompt: string,
): Promise<string> {
  const angles = [
    "Focus on correctness and edge cases.",
    "Focus on simplicity and readability.",
    "Focus on performance and efficiency.",
    "Focus on robustness and error handling.",
    "Focus on maintainability.",
  ];
  const workers: TaskInfo[] = [];
  for (let i = 0; i < n; i++) {
    workers.push(await spawnWorker(`${angles[i % angles.length]}\n\n${task}`, workerModel));
  }
  const results = await Promise.all(workers.map(waitForTask));
  const outputs = results.map((r, i) =>
    `## Worker ${i + 1} (${angles[i % angles.length]})\n\n${getResult(r)}`
  ).join("\n\n---\n\n");
  const reviewTask = `${reviewerPrompt}\n\n# Original Task\n${task}\n\n# Worker Outputs\n${outputs}`;
  return getResult(await waitForTask(await spawnWorker(reviewTask, reviewerModel)));
}

// ── Tree Dispatch ───────────────────────────────────────────────────────

function flattenSubagents(node: AgentNode): Array<{ name: string; agent: AgentNode }> {
  const result: Array<{ name: string; agent: AgentNode }> = [];
  if (node.subagents) {
    for (const [name, agent] of Object.entries(node.subagents)) {
      result.push({ name, agent });
    }
  }
  return result;
}

function buildAgentPrompt(name: string, agent: AgentNode, task: string): string {
  const prompt = resolvePrompt(agent.prompt);
  const parts = [prompt, "", `# Task\n${task}`];

  if (agent.domain?.write) {
    parts.push("", `# Domain Restriction\nYou may ONLY write to files matching: ${agent.domain.write.join(", ")}. Do NOT modify files outside this domain.`);
  }

  if (agent.subagents) {
    const subNames = Object.keys(agent.subagents);
    parts.push("", `# Your Subagents\nYou have subagents available: ${subNames.join(", ")}. Delegate subtasks to them via bg-agent.`);
  }

  return parts.join("\n");
}

async function dispatchTree(
  task: string,
  orchestrator: AgentNode,
  ctx: ExtensionContext,
): Promise<string> {
  const subagents = flattenSubagents(orchestrator);
  if (subagents.length === 0) {
    // Solo orchestrator — just run the task directly
    const model = await resolveModel(orchestrator.role, ctx);
    const fullPrompt = buildAgentPrompt("orchestrator", orchestrator, task);
    const info = await spawnWorker(fullPrompt, model);
    return getResult(await waitForTask(info));
  }

  // Spawn all subagents in parallel
  const tasks: Array<{ name: string; info: TaskInfo }> = [];
  for (const { name, agent } of subagents) {
    const model = await resolveModel(agent.role, ctx);
    const fullPrompt = buildAgentPrompt(name, agent, task);
    const info = await spawnWorker(fullPrompt, model);
    tasks.push({ name, info });
  }

  // Wait for all subagents
  const results = await Promise.all(
    tasks.map(async ({ name, info }) => ({
      name,
      result: await waitForTask(info),
    }))
  );

  // Orchestrator synthesizes
  const subagentOutputs = results.map(({ name, result }) =>
    `## ${name} [${result.status}]\n\n${getResult(result)}`
  ).join("\n\n---\n\n");

  const orchestratorPrompt = resolvePrompt(orchestrator.prompt);
  const synthTask = [
    orchestratorPrompt,
    "",
    "# Original Task",
    task,
    "",
    "# Subagent Results",
    subagentOutputs,
    "",
    "Synthesize the above into a coherent result. Resolve conflicts, fill gaps, produce the final output.",
  ].join("\n");

  const orchestratorModel = await resolveModel(orchestrator.role, ctx);
  const synthInfo = await spawnWorker(synthTask, orchestratorModel);
  return getResult(await waitForTask(synthInfo));
}

// ── Extension Entry ─────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  // Load teams config at startup
  pi.on("session_start", async (_event, ctx) => {
    teamsConfig = loadTeams();
    if (teamsConfig) {
      const teamNames = Object.keys(teamsConfig.teams);
      ctx.ui.setStatus(`teams: ${teamNames.length} loaded`, "agent-teams");
    }
  });

  // ── /team command — select active team ────────────────────────────────

  pi.registerCommand("team", {
    description: "Select a team from teams.yaml",
    handler: async (_args, ctx) => {
      teamsConfig = loadTeams(); // reload in case edited
      if (!teamsConfig || Object.keys(teamsConfig.teams).length === 0) {
        ctx.ui.notify("No teams.yaml found or no teams defined.", "warning");
        return;
      }

      const teamNames = Object.keys(teamsConfig.teams);
      const options = teamNames.map((name) => {
        const team = teamsConfig!.teams[name];
        const subCount = team.subagents ? Object.keys(team.subagents).length : 0;
        return subCount > 0
          ? `${name} (${subCount} subagents)`
          : `${name} (solo)`;
      });

      const choice = await ctx.ui.select("Select team", options);
      if (choice === undefined) return;

      activeTeamName = choice.split(" (")[0];
      ctx.ui.notify(`Active team: ${activeTeamName}`, "info");
      ctx.ui.setStatus(`team: ${activeTeamName}`, "agent-teams");
    },
  });

  // ── bg-dispatch — dispatch task to the active team's tree ─────────────

  pi.registerTool({
    name: "bg-dispatch",
    label: "Team Dispatch",
    description:
      "Dispatch a task to the active team (set via /team). The orchestrator " +
      "delegates to its subagents in parallel, then synthesizes results. " +
      "If no team is selected, lists available teams. " +
      "Use /team to switch teams.",
    parameters: Type.Object({
      task: Type.String({ description: "Task for the team to perform" }),
      team: Type.Optional(Type.String({
        description: "Team name (overrides /team selection)",
      })),
    }),

    async execute(_toolCallId, params, _signal, onUpdate, ctx) {
      teamsConfig = teamsConfig ?? loadTeams();
      if (!teamsConfig) {
        return {
          content: [{ type: "text" as const, text: "No teams.yaml found. Run the installer or create one at the workspace root." }],
        };
      }

      const teamName = params.team ?? activeTeamName;
      if (!teamName) {
        const names = Object.keys(teamsConfig.teams).join(", ");
        return {
          content: [{ type: "text" as const, text: `No team selected. Use /team or pass team parameter. Available: ${names}` }],
        };
      }

      const team = teamsConfig.teams[teamName];
      if (!team) {
        const names = Object.keys(teamsConfig.teams).join(", ");
        return {
          content: [{ type: "text" as const, text: `Team "${teamName}" not found. Available: ${names}` }],
        };
      }

      if (onUpdate) {
        const subCount = team.subagents ? Object.keys(team.subagents).length : 0;
        onUpdate({
          content: [{ type: "text" as const, text: `Dispatching to team "${teamName}" (${subCount} subagents)...` }],
          details: { team: teamName, status: "running" },
        });
      }

      try {
        const result = await dispatchTree(params.task, team, ctx);
        const truncated = result.length > 8000 ? result.slice(-8000) + "\n... [truncated]" : result;
        return {
          content: [{ type: "text" as const, text: truncated }],
          details: { team: teamName, status: "done" },
        };
      } catch (err: any) {
        return {
          content: [{ type: "text" as const, text: `Team dispatch failed: ${err.message}` }],
          details: { team: teamName, status: "failed", error: err.message },
        };
      }
    },

    renderCall(args, theme) {
      const teamLabel = args.team ?? activeTeamName ?? "?";
      return new Text(
        theme.fg("toolTitle", theme.bold("bg-dispatch ")) +
          theme.fg("accent", teamLabel) +
          theme.fg("dim", ` — ${args.task?.slice(0, 50) ?? ""}`),
        0, 0,
      );
    },

    renderResult(result, _options, theme) {
      const details = result.details as { team?: string; status?: string } | undefined;
      const icon = details?.status === "done" ? "✓" : "✗";
      const color = details?.status === "done" ? "success" : "error";
      return new Text(
        theme.fg(color, `${icon} `) +
          theme.fg("accent", details?.team ?? "team") +
          theme.fg("dim", ` ${details?.status ?? "unknown"}`),
        0, 0,
      );
    },
  });

  // ── bg-team — ad-hoc strategies (no teams.yaml needed) ────────────────

  pi.registerTool({
    name: "bg-team",
    label: "Team Strategy",
    description:
      "Run an ad-hoc multi-agent strategy without teams.yaml. " +
      "Strategies: best-of-n (pick best from N attempts), " +
      "debate (propose→critique→revise→synthesize), " +
      "ensemble (N different angles→synthesize). " +
      "For named teams, use bg-dispatch instead.",
    parameters: Type.Object({
      task: Type.String({ description: "Task for the team to perform" }),
      strategy: Type.Union([
        Type.Literal("best-of-n"),
        Type.Literal("debate"),
        Type.Literal("ensemble"),
      ], { description: "Team strategy" }),
      workers: Type.Optional(Type.Number({ description: "Number of parallel workers (default 3)", default: 3 })),
      rounds: Type.Optional(Type.Number({ description: "Debate rounds (default 1)", default: 1 })),
      reviewer_prompt: Type.Optional(Type.String({ description: "Custom reviewer prompt" })),
    }),

    async execute(_toolCallId, params, _signal, onUpdate, ctx) {
      const n = params.workers ?? 3;
      const rounds = params.rounds ?? 1;
      const reviewerPrompt = params.reviewer_prompt ??
        "Synthesize the best parts from all outputs into a single high-quality solution. Be concise.";

      const workerModel = await resolveModel("worker", ctx);
      const reviewerModel = await resolveModel("reviewer", ctx);
      if (!workerModel) {
        return { content: [{ type: "text" as const, text: "No worker model configured." }] };
      }

      if (onUpdate) {
        onUpdate({
          content: [{ type: "text" as const, text: `Starting ${params.strategy} with ${n} workers...` }],
          details: { strategy: params.strategy, workers: n, status: "running" },
        });
      }

      let result: string;
      try {
        switch (params.strategy) {
          case "best-of-n":
            result = await bestOfN(params.task, n, workerModel, reviewerModel, reviewerPrompt);
            break;
          case "debate":
            result = await debate(params.task, rounds, workerModel, reviewerModel, reviewerPrompt);
            break;
          case "ensemble":
            result = await ensemble(params.task, n, workerModel, reviewerModel, reviewerPrompt);
            break;
        }
      } catch (err: any) {
        return {
          content: [{ type: "text" as const, text: `Team failed: ${err.message}` }],
          details: { strategy: params.strategy, status: "failed" },
        };
      }

      const truncated = result.length > 8000 ? result.slice(-8000) + "\n... [truncated]" : result;
      return {
        content: [{ type: "text" as const, text: truncated }],
        details: { strategy: params.strategy, workers: n, status: "done" },
      };
    },

    renderCall(args, theme) {
      return new Text(
        theme.fg("toolTitle", theme.bold("bg-team ")) +
          theme.fg("accent", args.strategy) +
          theme.fg("dim", ` (${args.workers ?? 3} workers)`),
        0, 0,
      );
    },

    renderResult(result, _options, theme) {
      const details = result.details as { strategy?: string; status?: string } | undefined;
      const icon = details?.status === "done" ? "✓" : "✗";
      const color = details?.status === "done" ? "success" : "error";
      return new Text(
        theme.fg(color, `${icon} `) +
          theme.fg("accent", details?.strategy ?? "team") +
          theme.fg("dim", ` ${details?.status ?? "unknown"}`),
        0, 0,
      );
    },
  });
}
