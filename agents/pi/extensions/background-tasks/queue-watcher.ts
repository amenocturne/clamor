/**
 * Queue Watcher — Permission request monitoring
 *
 * Polls the permission queue directory for pending `.request.json` files from
 * subagents. When a request is found, it surfaces a UI prompt to the user
 * (allow/deny) and writes the response back for the subagent to pick up.
 * Also updates the parent task's `pendingPermissions` count.
 */

import type { ExtensionContext } from "@mariozechner/pi-coding-agent";
import {
  cleanupAll,
  scanRequests,
  writeResponse,
} from "../permission-queue/index.ts";
import type { PermissionResponse } from "../permission-queue/types.ts";
import { getTask } from "./task-manager.ts";

// ── State ───────────────────────────────────────────────────────────────

let watchInterval: ReturnType<typeof setInterval> | null = null;
const handledRequests = new Set<string>();

// ── Watcher ─────────────────────────────────────────────────────────────

export function startWatching(ctx: ExtensionContext): void {
  if (watchInterval) return;

  watchInterval = setInterval(() => {
    pollOnce(ctx);
  }, 500);
}

export function stopWatching(): void {
  if (watchInterval) {
    clearInterval(watchInterval);
    watchInterval = null;
  }
  handledRequests.clear();
}

export function cleanupQueue(): void {
  stopWatching();
  cleanupAll();
}

// ── Poll Logic ──────────────────────────────────────────────────────────

function pollOnce(ctx: ExtensionContext): void {
  const requests = scanRequests();

  for (const req of requests) {
    const key = `${req.taskId}:${req.id}`;
    if (handledRequests.has(key)) continue;
    handledRequests.add(key);

    // Update the parent task's pending count
    const task = getTask(req.taskId);
    if (task) {
      task.pendingPermissions++;
    }

    // Surface to user
    handleRequest(ctx, req.id, req.taskId, req.toolName, req.toolInput);
  }
}

async function handleRequest(
  ctx: ExtensionContext,
  requestId: string,
  taskId: string,
  toolName: string,
  toolInput: Record<string, unknown>,
): Promise<void> {
  const summary = formatToolSummary(toolName, toolInput);

  let decision: "allow" | "deny" = "deny";

  if (ctx.hasUI) {
    const choices = [
      `Allow: ${toolName} ${summary}`,
      "Deny",
    ];

    const selected = await ctx.ui.select(
      `Permission request from subagent ${taskId}`,
      choices,
    );

    decision = selected?.startsWith("Allow") ? "allow" : "deny";
  } else {
    // Non-interactive mode: auto-deny for safety
    decision = "deny";
  }

  const response: PermissionResponse = {
    id: requestId,
    decision,
    respondedAt: new Date().toISOString(),
  };

  writeResponse(response, taskId);

  // Decrement pending count
  const task = getTask(taskId);
  if (task && task.pendingPermissions > 0) {
    task.pendingPermissions--;
  }
}

// ── Helpers ─────────────────────────────────────────────────────────────

function formatToolSummary(
  toolName: string,
  toolInput: Record<string, unknown>,
): string {
  switch (toolName) {
    case "bash":
      return truncate(String(toolInput.command ?? ""), 60);
    case "read":
      return truncate(String(toolInput.file_path ?? toolInput.path ?? ""), 60);
    case "write":
    case "edit":
      return truncate(String(toolInput.file_path ?? toolInput.path ?? ""), 60);
    case "grep":
    case "find":
      return truncate(String(toolInput.pattern ?? toolInput.path ?? ""), 60);
    case "ls":
      return truncate(String(toolInput.path ?? "."), 60);
    default:
      return truncate(JSON.stringify(toolInput), 60);
  }
}

function truncate(s: string, maxLen: number): string {
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen - 3) + "...";
}
