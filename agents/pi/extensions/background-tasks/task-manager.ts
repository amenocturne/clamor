/**
 * Task Manager — Process spawning and lifecycle tracking
 *
 * Manages background shell commands and Pi subagent processes. Each task gets
 * a unique ID, accumulates stdout/stderr, and tracks status transitions.
 * The subagent spawner runs `pi` in JSON mode with the permission-gate extension
 * so permission requests bubble up to the main session via the permission queue.
 */

import { type ChildProcess, spawn } from "child_process";

// ── Types ───────────────────────────────────────────────────────────────

export type TaskStatus = "running" | "waiting" | "done" | "failed" | "killed";
export type TaskType = "command" | "agent";

export interface TaskInfo {
  id: string;
  type: TaskType;
  command: string;
  status: TaskStatus;
  startedAt: string;
  finishedAt?: string;
  exitCode?: number;
  output: string;
  errors: string;
  pid?: number;
  pendingPermissions: number;
  /** For agents: only the final assistant text (not tool history) */
  finalReport: string;
}

// ── Registry ────────────────────────────────────────────────────────────

const taskRegistry = new Map<string, TaskInfo>();
const processRegistry = new Map<string, ChildProcess>();
let taskCounter = 0;
let onTaskComplete: ((task: TaskInfo) => void) | null = null;

/** Register a callback invoked when any task finishes (done/failed). */
export function setOnTaskComplete(cb: (task: TaskInfo) => void): void {
  onTaskComplete = cb;
}

// ── ID Generation ───────────────────────────────────────────────────────

export function generateTaskId(): string {
  taskCounter++;
  return `t${taskCounter}`;
}

// ── Command Spawning ────────────────────────────────────────────────────

export function spawnCommand(id: string, command: string, cwd: string): TaskInfo {
  const info: TaskInfo = {
    id,
    type: "command",
    command,
    status: "running",
    startedAt: new Date().toISOString(),
    output: "",
    errors: "",
    pendingPermissions: 0,
    finalReport: "",
  };

  taskRegistry.set(id, info);

  const proc = spawn("sh", ["-c", command], {
    cwd,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env },
  });

  info.pid = proc.pid;
  processRegistry.set(id, proc);

  proc.stdout!.setEncoding("utf-8");
  proc.stdout!.on("data", (chunk: string) => {
    info.output += chunk;
  });

  proc.stderr!.setEncoding("utf-8");
  proc.stderr!.on("data", (chunk: string) => {
    info.errors += chunk;
  });

  proc.on("close", (code) => {
    info.exitCode = code ?? undefined;
    if (info.status !== "killed") {
      info.status = code === 0 ? "done" : "failed";
    }
    info.finishedAt = info.finishedAt ?? new Date().toISOString();
    processRegistry.delete(id);
    onTaskComplete?.(info);
  });

  proc.on("error", (err) => {
    if (info.status !== "killed") {
      info.status = "failed";
    }
    info.errors += `\nProcess error: ${err.message}`;
    info.finishedAt = info.finishedAt ?? new Date().toISOString();
    processRegistry.delete(id);
    onTaskComplete?.(info);
  });

  return info;
}

// ── Agent Spawning ──────────────────────────────────────────────────────

// Stagger parallel agent spawns to avoid lock contention on Pi's config/auth files
let lastAgentSpawnTime = 0;
const SPAWN_STAGGER_MS = 500;

export async function spawnAgent(
  id: string,
  task: string,
  model: string,
  cwd: string,
  extensionPaths: string[],
): Promise<TaskInfo> {
  const info: TaskInfo = {
    id,
    type: "agent",
    command: task,
    status: "running",
    startedAt: new Date().toISOString(),
    output: "",
    errors: "",
    pendingPermissions: 0,
    finalReport: "",
  };

  taskRegistry.set(id, info);

  // Stagger: wait if another agent was spawned recently
  const now = Date.now();
  const elapsed = now - lastAgentSpawnTime;
  if (elapsed < SPAWN_STAGGER_MS) {
    await new Promise((r) => setTimeout(r, SPAWN_STAGGER_MS - elapsed));
  }
  lastAgentSpawnTime = Date.now();

  const extensionArgs = extensionPaths.flatMap((p) => ["-e", p]);

  const proc = spawn(
    "pi",
    [
      "--mode", "json",
      "-p",
      "--no-extensions",
      ...extensionArgs,
      "--model", model,
      "--tools", "read,write,edit,bash,grep,find,ls",
      "--thinking", "off",
      task,
    ],
    {
      cwd,
      stdio: ["ignore", "pipe", "pipe"],
      env: {
        ...process.env,
        AGENTIC_KIT_TASK_ID: id,
      },
    },
  );

  info.pid = proc.pid;
  processRegistry.set(id, proc);

  let buffer = "";

  proc.stdout!.setEncoding("utf-8");
  proc.stdout!.on("data", (chunk: string) => {
    buffer += chunk;
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      processJsonLine(info, line);
    }
  });

  proc.stderr!.setEncoding("utf-8");
  proc.stderr!.on("data", (chunk: string) => {
    info.errors += chunk;
  });

  proc.on("close", (code) => {
    if (buffer.trim()) processJsonLine(info, buffer);
    info.exitCode = code ?? undefined;
    if (info.status !== "killed") {
      info.status = code === 0 ? "done" : "failed";
    }
    info.finishedAt = info.finishedAt ?? new Date().toISOString();
    processRegistry.delete(id);
    onTaskComplete?.(info);
  });

  proc.on("error", (err) => {
    if (info.status !== "killed") {
      info.status = "failed";
    }
    info.errors += `\nProcess error: ${err.message}`;
    info.finishedAt = new Date().toISOString();
    processRegistry.delete(id);
    onTaskComplete?.(info);
  });

  return info;
}

// ── JSON Event Parsing ──────────────────────────────────────────────────

/** Track current message text — reset on each new assistant message */
const agentCurrentMessage = new Map<string, string>();

function processJsonLine(info: TaskInfo, line: string): void {
  if (!line.trim()) return;
  try {
    const event = JSON.parse(line);
    const type = event.type;

    if (type === "message_update") {
      const delta = event.assistantMessageEvent;
      if (delta?.type === "text_delta" && typeof delta.delta === "string") {
        info.output += delta.delta;
        // Accumulate current message text
        const current = agentCurrentMessage.get(info.id) ?? "";
        agentCurrentMessage.set(info.id, current + delta.delta);
      }
    } else if (type === "message_end") {
      // Save the completed message as the latest report
      const msg = agentCurrentMessage.get(info.id);
      if (msg) {
        info.finalReport = msg;
      }
      agentCurrentMessage.delete(info.id);
    } else if (type === "tool_execution_start") {
      // New tool call means a new turn is starting — reset current message
      agentCurrentMessage.delete(info.id);
    }
  } catch {
    // Not JSON — treat as raw output
    info.output += line + "\n";
  }
}

// ── Queries ─────────────────────────────────────────────────────────────

export function getTask(id: string): TaskInfo | undefined {
  return taskRegistry.get(id);
}

export function getAllTasks(): TaskInfo[] {
  return Array.from(taskRegistry.values());
}

// ── Kill ─────────────────────────────────────────────────────────────────

export function killTask(id: string): boolean {
  const proc = processRegistry.get(id);
  const info = taskRegistry.get(id);

  if (!proc || !info) return false;

  try {
    proc.kill("SIGTERM");
    info.status = "killed";
    info.finishedAt = new Date().toISOString();
    processRegistry.delete(id);
    return true;
  } catch {
    return false;
  }
}

// ── Cleanup ─────────────────────────────────────────────────────────────

export function killAllTasks(): void {
  for (const [id, proc] of processRegistry) {
    try {
      proc.kill("SIGTERM");
    } catch {}
    const info = taskRegistry.get(id);
    if (info && info.status === "running") {
      info.status = "killed";
      info.finishedAt = new Date().toISOString();
    }
  }
  processRegistry.clear();
}

export function clearRegistry(): void {
  killAllTasks();
  taskRegistry.clear();
  taskCounter = 0;
}
