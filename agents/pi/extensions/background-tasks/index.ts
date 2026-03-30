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
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";
import { cleanupQueue, startWatching, stopWatching } from "./queue-watcher.ts";
import {
  generateTaskId,
  getAllTasks,
  getTask,
  killAllTasks,
  killTask,
  spawnAgent,
  spawnCommand,
  type TaskInfo,
} from "./task-manager.ts";

// ── Extension Root ──────────────────────────────────────────────────────

const __dirname = dirname(fileURLToPath(import.meta.url));
const permissionGatePath = resolve(__dirname, "../permission-gate");
const nestorProviderPath = resolve(__dirname, "../nestor-provider");

// ── Widget State ────────────────────────────────────────────────────────

let widgetCtx: ExtensionContext | null = null;
let widgetRefreshInterval: ReturnType<typeof setInterval> | null = null;

// ── Widget Rendering ────────────────────────────────────────────────────

function updateWidget(): void {
  if (!widgetCtx) return;

  const tasks = getAllTasks();

  if (tasks.length === 0) {
    widgetCtx.ui.setWidget("bg-tasks", undefined);
    stopWidgetRefresh();
    return;
  }

  widgetCtx.ui.setWidget(
    "bg-tasks",
    (_tui, theme) => {
      const container = new Container();
      container.addChild(new Text("", 0, 0));
      container.addChild(new DynamicBorder((s) => theme.fg("dim", s)));
      const content = new Text("", 1, 0);
      container.addChild(content);
      container.addChild(new DynamicBorder((s) => theme.fg("dim", s)));

      return {
        render(width: number): string[] {
          const currentTasks = getAllTasks();
          const running = currentTasks.filter((t) => t.status === "running").length;
          const header =
            theme.fg("accent", `Background Tasks (${currentTasks.length})`) +
            (running > 0 ? theme.fg("dim", ` - ${running} running`) : "");

          const lines: string[] = [header];

          for (const t of currentTasks) {
            lines.push(formatTaskLine(t, width, theme));
          }

          content.setText(lines.join("\n"));
          return container.render(width);
        },
        invalidate() {
          container.invalidate();
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
  const typePrefix = task.type === "agent" ? "Agent: " : "";
  const commandPreview = truncateToWidth(
    `${typePrefix}${task.command}`,
    Math.max(20, width - 30),
  );

  let line =
    `  ${theme.fg("accent", task.id)} ` +
    `${theme.fg(statusColor, `[${task.status}]`)} ` +
    `${theme.fg("dim", elapsed.padStart(4))}  ` +
    `${theme.fg("muted", commandPreview)}`;

  if (task.pendingPermissions > 0) {
    line += theme.fg("warning", ` ! ${task.pendingPermissions} pending permission${task.pendingPermissions > 1 ? "s" : ""}`);
  }

  return line;
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

// ── Extension Entry Point ───────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  // ── bg-run ──────────────────────────────────────────────────────────

  pi.registerTool({
    name: "bg-run",
    label: "Background Run",
    description:
      "Run a shell command in the background. Returns a task ID immediately — " +
      "use bg-status or bg-result to check progress later.",
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
      "Returns a task ID immediately — use bg-status or bg-result to check progress.",
    parameters: Type.Object({
      task: Type.String({
        description: "Task description for the subagent to perform",
      }),
    }),

    async execute(_toolCallId, params, _signal, _onUpdate, ctx) {
      widgetCtx = ctx;
      const id = generateTaskId();
      const cwd = process.cwd();
      const model = ctx.model
        ? `${ctx.model.provider}/${ctx.model.id}`
        : "openrouter/google/gemini-3-flash-preview";

      const extensionPaths = [permissionGatePath, nestorProviderPath];
      const info = spawnAgent(id, params.task, model, cwd, extensionPaths);

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

  pi.registerTool({
    name: "bg-status",
    label: "Background Status",
    description:
      "List all background tasks with their current status, elapsed time, " +
      "and pending permission request count.",
    parameters: Type.Object({}),

    async execute() {
      const tasks = getAllTasks();
      const text = formatTaskTable(tasks);

      return {
        content: [{ type: "text" as const, text }],
        details: {
          count: tasks.length,
          tasks: tasks.map((t) => ({
            id: t.id,
            type: t.type,
            status: t.status,
            elapsed: formatElapsed(t),
            pendingPermissions: t.pendingPermissions,
            command:
              t.command.length > 80
                ? t.command.slice(0, 77) + "..."
                : t.command,
          })),
        },
      };
    },

    renderCall(_args, theme) {
      return new Text(
        theme.fg("toolTitle", theme.bold("bg-status")),
        0,
        0,
      );
    },

    renderResult(result, { expanded }, theme) {
      const details = result.details as
        | { count: number; tasks: any[] }
        | undefined;
      if (!details || details.count === 0) {
        return new Text(theme.fg("dim", "No background tasks."), 0, 0);
      }

      const lines = details.tasks.map((t: any) => {
        const statusColor =
          t.status === "running" ? "accent"
          : t.status === "done" ? "success"
          : "error";
        let line = `${theme.fg("accent", t.id)} ${theme.fg(statusColor, `[${t.status}]`)} ${theme.fg("dim", t.elapsed)} ${theme.fg("muted", t.command)}`;
        if (t.pendingPermissions > 0) {
          line += theme.fg("warning", ` ! ${t.pendingPermissions} pending`);
        }
        return line;
      });

      const display = expanded ? lines : lines.slice(0, 5);
      let text = display.join("\n");
      if (!expanded && lines.length > 5) {
        text += `\n${theme.fg("dim", `... ${lines.length - 5} more`)}`;
      }

      return new Text(text, 0, 0);
    },
  });

  // ── bg-result ───────────────────────────────────────────────────────

  pi.registerTool({
    name: "bg-result",
    label: "Background Result",
    description:
      "Get the full output of a background task by ID. Returns stdout, stderr, " +
      "exit code, and status. If the task is still running, returns output so far.",
    parameters: Type.Object({
      id: Type.String({ description: "Task ID (e.g. t1, t2)" }),
    }),

    async execute(_toolCallId, params) {
      const task = getTask(params.id);
      if (!task) {
        return {
          content: [
            {
              type: "text" as const,
              text: `No task found with ID "${params.id}". Use bg-status to list tasks.`,
            },
          ],
        };
      }

      return {
        content: [{ type: "text" as const, text: formatTaskResult(task) }],
        details: {
          id: task.id,
          type: task.type,
          status: task.status,
          exitCode: task.exitCode,
          pendingPermissions: task.pendingPermissions,
        },
      };
    },

    renderCall(args, theme) {
      return new Text(
        theme.fg("toolTitle", theme.bold("bg-result ")) +
          theme.fg("accent", args.id),
        0,
        0,
      );
    },

    renderResult(result, { expanded }, theme) {
      const details = result.details as Record<string, unknown> | undefined;
      if (!details) {
        return new Text(
          theme.fg("error", result.content[0]?.type === "text" ? (result.content[0] as any).text : "Not found"),
          0,
          0,
        );
      }

      const statusColor =
        details.status === "running" ? "accent"
        : details.status === "done" ? "success"
        : "error";

      let summary =
        theme.fg("accent", `${details.id}`) +
        ` ${theme.fg(statusColor, `[${details.status}]`)}`;

      if (details.exitCode !== undefined) {
        summary += theme.fg("dim", ` exit=${details.exitCode}`);
      }

      if (!expanded) return new Text(summary, 0, 0);

      const fullText = result.content[0]?.type === "text" ? (result.content[0] as any).text : "";
      return new Text(summary + "\n" + theme.fg("dim", fullText), 0, 0);
    },
  });

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

  // ── Event Hooks ───────────────────────────────────────────────────────

  pi.on("session_start", async (_event, ctx) => {
    widgetCtx = ctx;
    startWatching(ctx);
    updateWidget();
    ctx.ui.setStatus("bg: idle", "bg-tasks");
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
