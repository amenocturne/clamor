/**
 * Background Tasks — Pi Extension
 *
 * Provides tools for running shell commands and Pi subagent processes in the
 * background. The agent receives a task ID immediately and checks status/results
 * later. Permission requests from subagents are monitored and surfaced to the
 * user via the permission queue watcher.
 *
 * Tools: bg-run, bg-agent, bg-status, bg-result, bg-kill
 * Widget: live task list below the editor
 * Command: /bg — show task summary
 *
 * Usage: pi -e agents/pi/extensions/background-tasks
 */

import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { DynamicBorder } from "@mariozechner/pi-coding-agent";
import { Container, Text, truncateToWidth } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";
import { existsSync, readdirSync } from "fs";
import { dirname, join, resolve } from "path";
import { fileURLToPath } from "url";
import { cleanupQueue, startWatching, stopWatching } from "./queue-watcher.ts";
import {
  generateTaskId,
  getAllTasks,
  getTask,
  killAllTasks,
  killTask,
  setOnTaskComplete,
  spawnAgent,
  spawnCommand,
  type TaskInfo,
} from "./task-manager.ts";

// ── Extension Root ──────────────────────────────────────────────────────

const __dirname = dirname(fileURLToPath(import.meta.url));
const permissionGatePath = resolve(__dirname, "../permission-gate");

/**
 * Discover extensions to pass to subagents.
 * First tries -e flags from process.argv (explicit launch).
 * Falls back to scanning .pi/extensions/ directory (auto-discovery).
 * Excludes background-tasks itself to prevent recursive spawning.
 */
function getExtensionsForSubagent(cwd: string): string[] {
  const selfName = "background-tasks";

  // Try explicit -e flags first
  const argv = process.argv;
  const explicit: string[] = [];
  for (let i = 0; i < argv.length - 1; i++) {
    if (argv[i] === "-e" || argv[i] === "--extension") {
      const p = resolve(argv[i + 1]);
      if (!p.includes(selfName)) explicit.push(p);
    }
  }
  if (explicit.length > 0) return explicit;

  // Fall back: scan .pi/extensions/ directory
  const extDir = join(cwd, ".pi", "extensions");
  if (!existsSync(extDir)) return [permissionGatePath];

  const paths: string[] = [];
  for (const entry of readdirSync(extDir)) {
    if (entry === selfName) continue;
    const full = resolve(extDir, entry);
    // Only include directories that look like extensions (have index.ts or package.json)
    if (existsSync(join(full, "index.ts")) || existsSync(join(full, "package.json"))) {
      paths.push(full);
    }
  }

  return paths.length > 0 ? paths : [permissionGatePath];
}

// ── Widget State ────────────────────────────────────────────────────────

let widgetCtx: ExtensionContext | null = null;
let widgetRefreshInterval: ReturnType<typeof setInterval> | null = null;

// ── Widget Rendering ────────────────────────────────────────────────────

/** Only show running tasks and recently finished ones (last 10s). */
function visibleTasks(): TaskInfo[] {
  const now = Date.now();
  return getAllTasks().filter((t) => {
    if (t.status === "running") return true;
    if (!t.finishedAt) return false;
    return now - new Date(t.finishedAt).getTime() < 10_000;
  });
}

function updateWidget(): void {
  if (!widgetCtx) return;

  const tasks = visibleTasks();

  if (tasks.length === 0) {
    widgetCtx.ui.setWidget("bg-tasks", undefined);
    stopWidgetRefresh();
    return;
  }

  widgetCtx.ui.setWidget(
    "bg-tasks",
    (_tui, theme) => {
      const text = new Text("", 0, 0);

      return {
        render(width: number): string[] {
          const currentTasks = visibleTasks();
          if (currentTasks.length === 0) return [];

          const lines = currentTasks.map((t) => formatTaskLine(t, width, theme));
          text.setText(lines.join("\n"));
          return text.render(width);
        },
        invalidate() {
          text.invalidate();
        },
      };
    },
    { placement: "belowEditor" },
  );

  startWidgetRefresh();
}

function formatTaskLine(
  task: TaskInfo,
  width: number,
  theme: any,
): string {
  const statusColor =
    task.status === "running" ? "accent"
    : task.status === "done" ? "success"
    : task.status === "waiting" ? "warning"
    : "error";

  const elapsed = formatElapsed(task);
  const typeIcon = task.type === "agent" ? "A" : "$";

  // Fixed-width prefix: "  t1 A [running]  12s  " (~25 chars visible)
  const prefix = `${task.id} ${typeIcon} [${task.status}] ${elapsed.padStart(4)}`;
  const prefixLen = prefix.length;

  // Command preview fills the rest
  const maxCmd = Math.max(10, width - prefixLen - 4);
  const cmdRaw = task.command.length > maxCmd
    ? task.command.slice(0, maxCmd - 3) + "..."
    : task.command;
  // Strip newlines from command preview
  const cmdClean = cmdRaw.replace(/\n/g, " ");

  return truncateToWidth(
    `  ${theme.fg("accent", task.id)} ${theme.fg("dim", typeIcon)} ${theme.fg(statusColor, `[${task.status}]`)} ${theme.fg("dim", elapsed.padStart(4))}  ${theme.fg("muted", cmdClean)}`,
    width,
  );
}

function formatElapsed(task: TaskInfo): string {
  const start = new Date(task.startedAt).getTime();
  const end = task.finishedAt
    ? new Date(task.finishedAt).getTime()
    : Date.now();
  const seconds = Math.round((end - start) / 1000);

  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m${secs}s`;
}

function startWidgetRefresh(): void {
  if (widgetRefreshInterval) return;
  widgetRefreshInterval = setInterval(() => {
    const tasks = getAllTasks();
    const hasRunning = tasks.some((t) => t.status === "running");
    if (hasRunning) {
      updateWidget();
    } else {
      stopWidgetRefresh();
    }
  }, 1000);
}

function stopWidgetRefresh(): void {
  if (widgetRefreshInterval) {
    clearInterval(widgetRefreshInterval);
    widgetRefreshInterval = null;
  }
}

// ── Format Helpers ──────────────────────────────────────────────────────

function formatTaskTable(tasks: TaskInfo[]): string {
  if (tasks.length === 0) return "No background tasks.";

  const lines = ["Background Tasks:", ""];

  for (const t of tasks) {
    const elapsed = formatElapsed(t);
    const typeLabel = t.type === "agent" ? "agent" : "cmd";
    const preview =
      t.command.length > 50 ? t.command.slice(0, 47) + "..." : t.command;
    let line = `  ${t.id}  [${t.status.padEnd(7)}]  ${typeLabel}  ${elapsed.padStart(6)}  ${preview}`;

    if (t.pendingPermissions > 0) {
      line += `  (${t.pendingPermissions} pending permission${t.pendingPermissions > 1 ? "s" : ""})`;
    }

    lines.push(line);
  }

  return lines.join("\n");
}

function formatTaskResult(task: TaskInfo): string {
  const lines: string[] = [];

  lines.push(`Task ${task.id} [${task.status}]`);
  lines.push(`Type: ${task.type}`);
  lines.push(`Command: ${task.command}`);
  lines.push(`Started: ${task.startedAt}`);

  if (task.finishedAt) lines.push(`Finished: ${task.finishedAt}`);
  if (task.exitCode !== undefined) lines.push(`Exit code: ${task.exitCode}`);
  if (task.pid !== undefined) lines.push(`PID: ${task.pid}`);

  if (task.status === "running") {
    lines.push("");
    lines.push("Task is still running. Output so far:");
  }

  if (task.output) {
    lines.push("");
    lines.push("--- stdout ---");
    // Limit output to last 8000 chars to avoid flooding
    const output = task.output.length > 8000
      ? "... [truncated]\n" + task.output.slice(-8000)
      : task.output;
    lines.push(output);
  }

  if (task.errors) {
    lines.push("");
    lines.push("--- stderr ---");
    const errors = task.errors.length > 4000
      ? "... [truncated]\n" + task.errors.slice(-4000)
      : task.errors;
    lines.push(errors);
  }

  return lines.join("\n");
}

function sendKilledMessage(pi: ExtensionAPI, content: string): void {
  pi.sendMessage(
    { customType: "bg-task-killed", content, display: true },
  );
}

// ── Extension Entry Point ───────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  // ── bg-run ──────────────────────────────────────────────────────────

  pi.registerTool({
    name: "bg-run",
    label: "Background Run",
    description:
      "Run a shell command in the background. Returns a task ID immediately. " +
      "Do NOT poll with bg-status/bg-result — you will be automatically notified " +
      "when the task completes with its full output. Continue other work or stop.",
    parameters: Type.Object({
      command: Type.String({
        description: "Shell command to execute in the background",
      }),
    }),

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      widgetCtx = ctx;
      const id = generateTaskId();
      const cwd = process.cwd();
      const info = spawnCommand(id, params.command, cwd);

      updateWidget();

      return {
        content: [
          {
            type: "text" as const,
            text: `Task ${id} started: ${params.command}`,
          },
        ],
        details: {
          taskId: id,
          command: params.command,
          status: info.status,
          pid: info.pid,
        },
      };
    },

    renderCall(args, theme) {
      return new Text(
        theme.fg("toolTitle", theme.bold("bg-run ")) +
          theme.fg("dim", args.command),
        0,
        0,
      );
    },

    renderResult(result, _options, theme) {
      const details = result.details as Record<string, unknown> | undefined;
      const taskId = details?.taskId ?? "?";
      return new Text(
        theme.fg("success", "-> ") +
          theme.fg("accent", `${taskId}`) +
          theme.fg("dim", " running"),
        0,
        0,
      );
    },
  });

  // ── bg-agent ────────────────────────────────────────────────────────

  pi.registerTool({
    name: "bg-agent",
    label: "Background Agent",
    description:
      "Spawn a Pi subagent in the background to perform a task autonomously. " +
      "The subagent has read, write, edit, bash, grep, find, and ls tools. " +
      "Permission requests from the subagent will be surfaced for approval. " +
      "Returns a task ID immediately. Do NOT poll — you will be automatically " +
      "notified when the agent finishes with its full output. Continue other work or stop.",
    parameters: Type.Object({
      task: Type.String({
        description: "Task description for the subagent to perform",
      }),
    }),

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      widgetCtx = ctx;
      if (!ctx.model) {
        return {
          content: [{ type: "text" as const, text: "No model configured. Select a model first (/model or settings.json)." }],
        };
      }

      const id = generateTaskId();
      const cwd = process.cwd();
      const model = `${ctx.model.provider}/${ctx.model.id}`;

      const extensionPaths = getExtensionsForSubagent(cwd);
      const info = await spawnAgent(id, params.task, model, cwd, extensionPaths);

      updateWidget();

      return {
        content: [
          {
            type: "text" as const,
            text: `Agent task ${id} started: ${params.task}`,
          },
        ],
        details: {
          taskId: id,
          task: params.task,
          status: info.status,
          pid: info.pid,
        },
      };
    },

    renderCall(args, theme) {
      const preview =
        args.task.length > 60 ? args.task.slice(0, 57) + "..." : args.task;
      return new Text(
        theme.fg("toolTitle", theme.bold("bg-agent ")) +
          theme.fg("dim", preview),
        0,
        0,
      );
    },

    renderResult(result, _options, theme) {
      const details = result.details as Record<string, unknown> | undefined;
      const taskId = details?.taskId ?? "?";
      return new Text(
        theme.fg("success", "-> ") +
          theme.fg("accent", `${taskId}`) +
          theme.fg("dim", " agent running"),
        0,
        0,
      );
    },
  });

  // ── bg-status ───────────────────────────────────────────────────────

  // bg-status and bg-result intentionally NOT registered as tools.
  // Results are pushed to the agent automatically on completion.
  // The /bg command is available for the USER to check status manually.

  // ── bg-kill ─────────────────────────────────────────────────────────

  pi.registerTool({
    name: "bg-kill",
    label: "Background Kill",
    description: "Kill a running background task by ID.",
    parameters: Type.Object({
      id: Type.String({ description: "Task ID to kill (e.g. t1, t2)" }),
    }),

    async execute(_toolCallId, params) {
      const task = getTask(params.id);
      if (!task) {
        return {
          content: [
            {
              type: "text" as const,
              text: `No task found with ID "${params.id}".`,
            },
          ],
        };
      }

      if (task.status !== "running") {
        return {
          content: [
            {
              type: "text" as const,
              text: `Task ${params.id} is not running (status: ${task.status}).`,
            },
          ],
        };
      }

      const killed = killTask(params.id);

      updateWidget();

      return {
        content: [
          {
            type: "text" as const,
            text: killed
              ? `Task ${params.id} killed.`
              : `Failed to kill task ${params.id}.`,
          },
        ],
        details: { id: params.id, killed },
      };
    },

    renderCall(args, theme) {
      return new Text(
        theme.fg("toolTitle", theme.bold("bg-kill ")) +
          theme.fg("error", args.id),
        0,
        0,
      );
    },

    renderResult(result, _options, theme) {
      const details = result.details as
        | { id: string; killed: boolean }
        | undefined;
      if (details?.killed) {
        return new Text(
          theme.fg("warning", "x ") +
            theme.fg("muted", `Task ${details.id} killed`),
          0,
          0,
        );
      }
      const text = result.content[0]?.type === "text" ? (result.content[0] as any).text : "Failed";
      return new Text(theme.fg("error", text), 0, 0);
    },
  });

  // ── /bg Command ─────────────────────────────────────────────────────

  pi.registerCommand("bg", {
    description: "List all background tasks",
    handler: async (_args, ctx) => {
      const tasks = getAllTasks();
      if (tasks.length === 0) {
        ctx.ui.notify("No background tasks.", "info");
        return;
      }

      const lines = tasks.map((t) => {
        const elapsed = formatElapsed(t);
        const typeLabel = t.type === "agent" ? "Agent: " : "";
        const preview =
          t.command.length > 40 ? t.command.slice(0, 37) + "..." : t.command;
        let line = `${t.id} [${t.status}] ${elapsed} ${typeLabel}${preview}`;
        if (t.pendingPermissions > 0) {
          line += ` (${t.pendingPermissions} pending)`;
        }
        return line;
      });

      ctx.ui.notify(
        `Background Tasks (${tasks.length}):\n${lines.join("\n")}`,
        "info",
      );
    },
  });

  // ── /kill Command ───────────────────────────────────────────────────

  pi.registerCommand("kill", {
    description: "Kill a running background task (or all)",
    handler: async (_args, ctx) => {
      const running = getAllTasks().filter((t) => t.status === "running");
      if (running.length === 0) {
        ctx.ui.notify("No running tasks.", "info");
        return;
      }

      const options = [
        ...running.map((t) => {
          const typeLabel = t.type === "agent" ? "Agent: " : "";
          const preview = t.command.length > 40 ? t.command.slice(0, 37) + "..." : t.command;
          return `${t.id} — ${typeLabel}${preview}`;
        }),
        "Kill all",
      ];

      const choice = await ctx.ui.select("Kill background task", options);
      if (choice === undefined) return;

      if (choice === "Kill all") {
        const ids = running.map((t) => t.id).join(", ");
        killAllTasks();
        sendKilledMessage(pi, `User killed all background tasks (${ids}). Do not retry or restart them unless the user asks.`);
      } else {
        const id = choice.split(" — ")[0];
        killTask(id);
        sendKilledMessage(pi, `User killed background task ${id}. Do not retry or restart it unless the user asks.`);
      }

      updateWidget();
    },
  });

  // Ctrl+X: kill all background tasks and abort current operation
  pi.registerShortcut("ctrl+x", {
    description: "Kill all background tasks and abort",
    handler: async (ctx) => {
      const running = getAllTasks().filter((t) => t.status === "running");

      if (running.length > 0) {
        const ids = running.map((t) => t.id).join(", ");
        killAllTasks();
        updateWidget();
        sendKilledMessage(pi, `User killed all background tasks (${ids}). Do not retry or restart them unless the user asks.`);
      }

      ctx.abort();
      ctx.ui.notify(
        running.length > 0
          ? `Aborted. Killed ${running.length} background task(s).`
          : "Aborted.",
        "warning",
      );
    },
  });

  // ── Event Hooks ───────────────────────────────────────────────────────

  pi.on("before_agent_start", async () => ({
    appendSystemPrompt:
      "## Background Tasks\n" +
      "ALWAYS use bg-run instead of the bash tool for ALL shell commands. " +
      "The bash tool blocks the session and cannot be cancelled. bg-run is non-blocking and killable (Ctrl+X).\n\n" +
      "### Rules\n" +
      "- Do NOT poll with bg-status or bg-result. Results are pushed to you automatically when each task completes.\n" +
      "- Each task delivers its own completion message. If you dispatched 3 tasks, you will receive 3 separate completion messages — one per task.\n" +
      "- Do NOT say all tasks are done after the first completion. Wait for ALL completion messages before summarizing.\n" +
      "- After dispatching, stop and wait. You will be triggered again for each completion.",
  }));

  pi.on("session_start", async (_event, ctx) => {
    widgetCtx = ctx;
    startWatching(ctx);
    updateWidget();
    ctx.ui.setStatus("bg: idle", "bg-tasks");

    // Push results into agent context when tasks complete
    setOnTaskComplete((task) => {
      updateWidget();

      // Killed tasks already notified from the kill handler — skip here
      if (task.status === "killed") return;

      const icon = task.status === "done" ? "✓" : "✗";
      const elapsed = formatElapsed(task);
      const typeLabel = task.type === "agent" ? "Agent task" : "Command";
      const allTasks = getAllTasks();
      const stillRunning = allTasks.filter((t) => t.status === "running").length;

      // For agents: use final report (last assistant message), not full tool history
      // For commands: use raw stdout
      const resultText = task.type === "agent" && task.finalReport
        ? task.finalReport
        : task.output;
      const truncatedResult = resultText.length > 6000
        ? resultText.slice(-6000) + "\n... [truncated]"
        : resultText;

      const remainingNote = stillRunning > 0
        ? `\n⏳ ${stillRunning} task(s) still running — wait for their completion messages before summarizing.`
        : "\n✓ All background tasks have completed.";

      const message = [
        `${icon} ${typeLabel} ${task.id} ${task.status === "done" ? "completed" : "failed"} (${elapsed})`,
        `Task: ${task.command}`,
        task.exitCode !== undefined ? `Exit code: ${task.exitCode}` : "",
        remainingNote,
        "",
        truncatedResult,
        task.errors ? `\n--- stderr ---\n${task.errors.slice(-2000)}` : "",
      ].filter(Boolean).join("\n");

      pi.sendMessage(
        {
          customType: "bg-task-complete",
          content: message,
          display: true,
        },
        { triggerTurn: true },
      );
    });
  });

  pi.on("agent_end", async (_event, _ctx) => {
    updateWidget();

    const tasks = getAllTasks();
    const running = tasks.filter((t) => t.status === "running").length;
    const total = tasks.length;

    if (widgetCtx) {
      if (total === 0) {
        widgetCtx.ui.setStatus("bg: idle", "bg-tasks");
      } else {
        widgetCtx.ui.setStatus(
          `bg: ${running} running / ${total} total`,
          "bg-tasks",
        );
      }
    }
  });

  // Cleanup on process exit
  process.on("exit", () => {
    killAllTasks();
    cleanupQueue();
  });

  process.on("SIGINT", () => {
    killAllTasks();
    cleanupQueue();
  });

  process.on("SIGTERM", () => {
    killAllTasks();
    cleanupQueue();
  });
}
