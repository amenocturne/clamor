/**
 * Queue Watcher — Permission request monitoring
 *
 * Polls the permission queue directory for pending `.request.json` files from
 * subagents. Requests are queued and processed one at a time (Pi's UI can
 * only show one prompt at a time). Writes responses back for subagents to
 * pick up and updates parent task's pendingPermissions count.
 */

import type { ExtensionContext } from "@mariozechner/pi-coding-agent";
import {
  cleanupAll,
  scanRequests,
  writeResponse,
} from "../permission-queue/index.ts";
import type { PermissionRequest, PermissionResponse } from "../permission-queue/types.ts";
import { getTask } from "./task-manager.ts";

// ── State ───────────────────────────────────────────────────────────────

let watchInterval: ReturnType<typeof setInterval> | null = null;
const handledRequests = new Set<string>();
const pendingQueue: PermissionRequest[] = [];
let processing = false;

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
  pendingQueue.length = 0;
  processing = false;
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

    const task = getTask(req.taskId);
    if (task) {
      task.pendingPermissions++;
    }

    pendingQueue.push(req);
  }

  // Process queue sequentially — one prompt at a time
  if (pendingQueue.length > 0 && !processing) {
    processNext(ctx);
  }
}

async function processNext(ctx: ExtensionContext): Promise<void> {
  if (pendingQueue.length === 0) {
    processing = false;
    return;
  }

  processing = true;
  const req = pendingQueue.shift()!;
  await handleRequest(ctx, req);

  // Continue to next request
  processNext(ctx);
}

async function handleRequest(
  ctx: ExtensionContext,
  req: PermissionRequest,
): Promise<void> {
  const summary = formatToolSummary(req.toolName, req.toolInput);
  const queuedCount = pendingQueue.length;
  const queueHint = queuedCount > 0 ? ` (+${queuedCount} queued)` : "";

  let decision: "allow" | "deny" = "deny";

  if (ctx.hasUI) {
    const confirmed = await ctx.ui.confirm(
      `Subagent ${req.taskId}: ${req.toolName}${queueHint}`,
      summary,
      { timeout: 120_000 },
    );
    decision = confirmed ? "allow" : "deny";
  }

  const response: PermissionResponse = {
    id: req.id,
    decision,
    respondedAt: new Date().toISOString(),
  };

  writeResponse(response, req.taskId);

  const task = getTask(req.taskId);
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
      return truncate(String(toolInput.command ?? ""), 120);
    case "read":
      return truncate(String(toolInput.file_path ?? toolInput.path ?? ""), 120);
    case "write":
    case "edit":
      return truncate(String(toolInput.file_path ?? toolInput.path ?? ""), 120);
    case "grep":
    case "find":
      return truncate(String(toolInput.pattern ?? toolInput.path ?? ""), 120);
    case "ls":
      return truncate(String(toolInput.path ?? "."), 120);
    default:
      return truncate(JSON.stringify(toolInput), 120);
  }
}

function truncate(s: string, maxLen: number): string {
  if (s.length <= maxLen) return s;
  return s.slice(0, maxLen - 3) + "...";
}
