/**
 * Agent Teams — Pi Extension
 *
 * Provides the `bg-team` tool for multi-agent strategies:
 * - best-of-n: N workers on identical task, reviewer picks/synthesizes best
 * - debate: sequential adversarial (propose → critique → revise → synthesize)
 * - ensemble: N workers with angle variations, reviewer synthesizes
 *
 * Uses model-router for role→model mapping and background-tasks' spawnAgent
 * for the actual process management.
 */

import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";
import { spawnAgent, generateTaskId, getTask, type TaskInfo } from "../background-tasks/task-manager.ts";

// ── Model Resolution ────────────────────────────────────────────────────

async function resolveModel(role: string, ctx: ExtensionContext): Promise<string> {
  try {
    const { getModelForRole } = await import("../model-router/index.ts");
    const model = getModelForRole(role);
    if (model) return model;
  } catch {}
  return ctx.model ? `${ctx.model.provider}/${ctx.model.id}` : "";
}

// ── Extension Discovery ─────────────────────────────────────────────────

function getExtensionsForWorker(): string[] {
  // Workers get permission-gate only — no background-tasks (prevents recursion)
  const { existsSync } = require("fs");
  const { join, resolve } = require("path");

  const extDir = join(process.cwd(), ".pi", "extensions");
  const selfNames = new Set(["background-tasks", "agent-teams"]);

  if (!existsSync(extDir)) return [];

  const paths: string[] = [];
  for (const entry of require("fs").readdirSync(extDir)) {
    if (selfNames.has(entry)) continue;
    const full = resolve(extDir, entry);
    if (existsSync(join(full, "index.ts")) || existsSync(join(full, "package.json"))) {
      paths.push(full);
    }
  }
  return paths;
}

// ── Worker Spawning ─────────────────────────────────────────────────────

async function spawnWorker(
  task: string,
  model: string,
  extensionPaths: string[],
): Promise<TaskInfo> {
  const id = generateTaskId();
  const cwd = process.cwd();
  return spawnAgent(id, task, model, cwd, extensionPaths, "silent");
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

// ── Strategies ──────────────────────────────────────────────────────────

async function bestOfN(
  task: string,
  n: number,
  workerModel: string,
  reviewerModel: string,
  reviewerPrompt: string,
  extensionPaths: string[],
): Promise<string> {
  // Spawn N workers with identical task
  const workers: TaskInfo[] = [];
  for (let i = 0; i < n; i++) {
    workers.push(await spawnWorker(task, workerModel, extensionPaths));
  }

  // Wait for all workers
  const results = await Promise.all(workers.map(waitForTask));

  // Build reviewer input
  const workerOutputs = results.map((r, i) =>
    `## Worker ${i + 1} [${r.status}]\n\n${getResult(r)}`
  ).join("\n\n---\n\n");

  const reviewTask = [
    reviewerPrompt,
    "",
    "# Original Task",
    task,
    "",
    "# Worker Outputs",
    workerOutputs,
  ].join("\n");

  // Spawn reviewer
  const reviewer = await spawnWorker(reviewTask, reviewerModel, extensionPaths);
  const reviewerResult = await waitForTask(reviewer);
  return getResult(reviewerResult);
}

async function debate(
  task: string,
  rounds: number,
  workerModel: string,
  reviewerModel: string,
  reviewerPrompt: string,
  extensionPaths: string[],
): Promise<string> {
  let proposalOutput = "";
  let critiqueOutput = "";

  for (let round = 0; round < rounds; round++) {
    // Agent A proposes (or revises)
    const proposeTask = round === 0
      ? task
      : [
          task,
          "",
          "# Previous Critique",
          "Address this critique and improve your solution:",
          critiqueOutput,
        ].join("\n");

    const proposer = await spawnWorker(proposeTask, workerModel, extensionPaths);
    const proposerResult = await waitForTask(proposer);
    proposalOutput = getResult(proposerResult);

    // Agent B critiques
    const critiqueTask = [
      "You are a critical reviewer. Find flaws, gaps, and improvements in this solution.",
      "",
      "# Original Task",
      task,
      "",
      "# Proposed Solution",
      proposalOutput,
      "",
      "Be specific about what's wrong and what's missing. Suggest concrete improvements.",
    ].join("\n");

    const critic = await spawnWorker(critiqueTask, workerModel, extensionPaths);
    const criticResult = await waitForTask(critic);
    critiqueOutput = getResult(criticResult);
  }

  // Final reviewer synthesizes
  const reviewTask = [
    reviewerPrompt,
    "",
    "# Original Task",
    task,
    "",
    "# Final Proposal",
    proposalOutput,
    "",
    "# Final Critique",
    critiqueOutput,
  ].join("\n");

  const reviewer = await spawnWorker(reviewTask, reviewerModel, extensionPaths);
  const reviewerResult = await waitForTask(reviewer);
  return getResult(reviewerResult);
}

async function ensemble(
  task: string,
  n: number,
  workerModel: string,
  reviewerModel: string,
  reviewerPrompt: string,
  extensionPaths: string[],
): Promise<string> {
  const angles = [
    "Focus on correctness and edge cases above all else.",
    "Focus on simplicity and readability — prefer the most straightforward approach.",
    "Focus on performance and efficiency — minimize unnecessary work.",
    "Focus on robustness and error handling — consider what could go wrong.",
    "Focus on maintainability — make it easy for others to understand and modify.",
  ];

  // Spawn N workers with different angle prompts
  const workers: TaskInfo[] = [];
  for (let i = 0; i < n; i++) {
    const angle = angles[i % angles.length];
    const angledTask = `${angle}\n\n${task}`;
    workers.push(await spawnWorker(angledTask, workerModel, extensionPaths));
  }

  // Wait for all workers
  const results = await Promise.all(workers.map(waitForTask));

  // Build reviewer input
  const workerOutputs = results.map((r, i) => {
    const angle = angles[i % angles.length];
    return `## Worker ${i + 1} (${angle.split(" — ")[0]})\n\n${getResult(r)}`;
  }).join("\n\n---\n\n");

  const reviewTask = [
    reviewerPrompt,
    "",
    "# Original Task",
    task,
    "",
    "# Worker Outputs (different perspectives)",
    workerOutputs,
  ].join("\n");

  const reviewer = await spawnWorker(reviewTask, reviewerModel, extensionPaths);
  const reviewerResult = await waitForTask(reviewer);
  return getResult(reviewerResult);
}

// ── Extension Entry ─────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  pi.registerTool({
    name: "bg-team",
    label: "Team Strategy",
    description:
      "Run a multi-agent team strategy. Spawns parallel workers and a reviewer " +
      "to synthesize results. Strategies: best-of-n (pick best from N attempts), " +
      "debate (propose→critique→revise→synthesize), ensemble (N different angles→synthesize). " +
      "This tool blocks until the team completes and returns the reviewer's output.",
    parameters: Type.Object({
      task: Type.String({ description: "Task for the team to perform" }),
      strategy: Type.Union([
        Type.Literal("best-of-n"),
        Type.Literal("debate"),
        Type.Literal("ensemble"),
      ], { description: "Team strategy" }),
      workers: Type.Optional(Type.Number({
        description: "Number of parallel workers (default 3)", default: 3,
      })),
      rounds: Type.Optional(Type.Number({
        description: "Number of debate rounds (debate strategy only, default 1)", default: 1,
      })),
      reviewer_prompt: Type.Optional(Type.String({
        description: "Custom prompt for the reviewer agent",
      })),
    }),

    async execute(_toolCallId, params, _signal, onUpdate, ctx) {
      const workerCount = params.workers ?? 3;
      const rounds = params.rounds ?? 1;
      const reviewerPrompt = params.reviewer_prompt ??
        "You are a senior reviewer. Synthesize the best parts from all worker outputs into a single, high-quality solution. Be concise and actionable.";

      const workerModel = await resolveModel("worker", ctx);
      const reviewerModel = await resolveModel("reviewer", ctx);

      if (!workerModel) {
        return {
          content: [{ type: "text" as const, text: "No model configured for workers. Set modelRouter.worker in settings.json or select a model." }],
        };
      }

      const extensionPaths = getExtensionsForWorker();

      if (onUpdate) {
        onUpdate({
          content: [{ type: "text" as const, text: `Starting ${params.strategy} with ${workerCount} workers...` }],
          details: { strategy: params.strategy, workers: workerCount, status: "running" },
        });
      }

      let result: string;
      try {
        switch (params.strategy) {
          case "best-of-n":
            result = await bestOfN(params.task, workerCount, workerModel, reviewerModel, reviewerPrompt, extensionPaths);
            break;
          case "debate":
            result = await debate(params.task, rounds, workerModel, reviewerModel, reviewerPrompt, extensionPaths);
            break;
          case "ensemble":
            result = await ensemble(params.task, workerCount, workerModel, reviewerModel, reviewerPrompt, extensionPaths);
            break;
        }
      } catch (err: any) {
        return {
          content: [{ type: "text" as const, text: `Team failed: ${err.message}` }],
          details: { strategy: params.strategy, status: "failed", error: err.message },
        };
      }

      const truncated = result.length > 8000
        ? result.slice(-8000) + "\n... [truncated]"
        : result;

      return {
        content: [{ type: "text" as const, text: truncated }],
        details: { strategy: params.strategy, workers: workerCount, status: "done" },
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
