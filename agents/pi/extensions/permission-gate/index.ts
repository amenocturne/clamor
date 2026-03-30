/**
 * Permission Gate — Pi extension for tool call interception
 *
 * Intercepts all tool calls, runs configured agentic-kit hooks (smart-approve,
 * deny-read, etc.) as subprocesses, and blocks/allows based on their output.
 *
 * When no hook has an opinion:
 * - Interactive (main session): enqueues into the unified permission queue
 *   (shared with subagent requests) for sequential user prompting.
 * - Non-interactive (subagent): writes to the file-based permission queue
 *   for the main session to handle.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { randomUUID } from "crypto";
import { resolve } from "path";
import { loadHookConfig, findMatchingHooks } from "./config.ts";
import type { HookConfig } from "./config.ts";
import { runHook } from "./hook-runner.ts";
import { writeRequest, waitForResponse } from "../permission-queue/index.ts";
import type { PermissionRequest } from "../permission-queue/types.ts";

/** Tools that only read — safe to auto-allow within project dir */
const READ_ONLY_TOOLS = new Set(["read", "grep", "find", "ls"]);

/** Tools that modify files — also safe within project dir */
const FILE_TOOLS = new Set(["read", "write", "edit", "grep", "find", "ls"]);

/** Extension-registered tools that handle their own permissions — skip the gate */
const PASSTHROUGH_TOOLS = new Set([
  "bg-run", "bg-agent", "bg-status", "bg-result", "bg-kill",
]);

/**
 * Try to import enqueuePermission from the sibling background-tasks extension.
 * This is the unified permission queue that processes prompts one at a time.
 * Falls back to direct ctx.ui.confirm() if background-tasks isn't loaded.
 */
let enqueuePermission: ((toolName: string, toolInput: Record<string, unknown>) => Promise<"allow" | "deny">) | null = null;

try {
  const qw = await import("../background-tasks/queue-watcher.ts");
  enqueuePermission = qw.enqueuePermission;
} catch {
  // background-tasks not available — will fall back to direct prompting
}

export default function (pi: ExtensionAPI) {
  let config: HookConfig = {};
  let interactive = true;
  let taskId: string | undefined;
  let cwd = ".";

  pi.on("session_start", async (_event, ctx) => {
    cwd = ctx.cwd;
    config = loadHookConfig(cwd);
    interactive = ctx.hasUI;
    taskId = process.env.AGENTIC_KIT_TASK_ID;

    const hookCount = countHooks(config);
    const mode = interactive ? "interactive" : taskId ? `subagent (task ${taskId})` : "subagent";

    ctx.ui.setStatus(
      "permission-gate",
      `Permission Gate: ${hookCount} hook${hookCount !== 1 ? "s" : ""} loaded (${mode})`,
    );
  });

  pi.on("tool_call", async (event, ctx) => {
    // Extension tools that manage their own permissions — don't gate them
    if (PASSTHROUGH_TOOLS.has(event.toolName)) {
      return { block: false };
    }

    const hooks = findMatchingHooks(config, event.toolName);
    const input = event.input as Record<string, unknown>;

    // Run matching hooks sequentially — deny takes priority
    for (const hook of hooks) {
      const result = await runHook(hook, event.toolName, input, cwd);

      if (result.decision === "deny") {
        logInterception(pi, event.toolName, input, "deny", result.reason);
        ctx.abort();
        return {
          block: true,
          reason: formatDenyReason(result.reason),
        };
      }

      if (result.decision === "allow") {
        logInterception(pi, event.toolName, input, "allow");
        return { block: false };
      }

      // "abstain" — continue to next hook
    }

    // Auto-allow file tools targeting paths within the project directory
    if (FILE_TOOLS.has(event.toolName) && isWithinProject(event.toolName, input, cwd)) {
      logInterception(pi, event.toolName, input, "allow", "within project dir");
      return { block: false };
    }

    // All hooks abstained — enqueue for user decision
    if (interactive) {
      // Use unified queue if available, fall back to direct prompt
      if (enqueuePermission) {
        const decision = await enqueuePermission(event.toolName, input);
        logInterception(pi, event.toolName, input, decision, "via permission queue");
        if (decision === "deny") {
          ctx.abort();
          return { block: true, reason: "Permission denied by user" };
        }
        return { block: false };
      }
      return promptUser(pi, ctx, event.toolName, input);
    }

    // Non-interactive (subagent): delegate to file-based permission queue
    if (taskId) {
      return requestPermission(pi, ctx, taskId, event.toolName, input);
    }

    // No hooks, not interactive, no task ID — block by default
    logInterception(pi, event.toolName, input, "deny", "No permission source available");
    ctx.abort();
    return {
      block: true,
      reason: "Permission denied: no hooks matched and no interactive session or task ID available",
    };
  });
}

function countHooks(config: HookConfig): number {
  if (!config.PreToolUse) return 0;
  return config.PreToolUse.reduce((sum, group) => sum + group.hooks.length, 0);
}

function formatDenyReason(reason?: string): string {
  const base = reason || "Denied by hook";
  return `Permission denied: ${base}\n\nDO NOT attempt to work around this restriction. Report this block to the user exactly as stated.`;
}

function logInterception(
  pi: ExtensionAPI,
  toolName: string,
  input: Record<string, unknown>,
  decision: string,
  reason?: string,
): void {
  pi.appendEntry("permission-gate-log", { tool: toolName, input, decision, reason });
}

/** Fallback: direct prompt when queue-watcher isn't available */
async function promptUser(
  pi: ExtensionAPI,
  ctx: any,
  toolName: string,
  input: Record<string, unknown>,
): Promise<{ block: boolean; reason?: string }> {
  const summary = formatToolSummary(toolName, input);
  const confirmed = await ctx.ui.confirm(
    "Permission Required",
    `${summary}\n\nAllow this tool call?`,
    { timeout: 60_000 },
  );

  if (confirmed) {
    logInterception(pi, toolName, input, "allow", "user approved");
    return { block: false };
  }

  logInterception(pi, toolName, input, "deny", "user denied");
  ctx.abort();
  return { block: true, reason: "Permission denied by user" };
}

/** Subagent mode: write to file queue, wait for main session response */
async function requestPermission(
  pi: ExtensionAPI,
  ctx: any,
  taskId: string,
  toolName: string,
  input: Record<string, unknown>,
): Promise<{ block: boolean; reason?: string }> {
  const requestId = randomUUID();
  const request: PermissionRequest = {
    id: requestId,
    taskId,
    toolName,
    toolInput: input,
    createdAt: new Date().toISOString(),
  };

  writeRequest(request);

  const response = await waitForResponse(taskId, requestId);

  if (!response) {
    logInterception(pi, toolName, input, "deny", "permission queue timeout");
    ctx.abort();
    return { block: true, reason: "Permission denied: no response from main session (timeout)" };
  }

  if (response.decision === "allow") {
    logInterception(pi, toolName, input, "allow", "approved via queue");
    return { block: false };
  }

  logInterception(pi, toolName, input, "deny", response.reason || "denied via queue");
  ctx.abort();
  return { block: true, reason: response.reason || "Permission denied by main session" };
}

function isWithinProject(toolName: string, input: Record<string, unknown>, cwd: string): boolean {
  const resolvedCwd = resolve(cwd);
  const rawPath = (input.file_path ?? input.path ?? "") as string;
  if (!rawPath) {
    return READ_ONLY_TOOLS.has(toolName);
  }
  try {
    const resolved = resolve(cwd, rawPath);
    return resolved.startsWith(resolvedCwd + "/") || resolved === resolvedCwd;
  } catch {
    return false;
  }
}

function formatToolSummary(toolName: string, input: Record<string, unknown>): string {
  switch (toolName) {
    case "bash":
      return `bash: ${String(input.command ?? "").slice(0, 200)}`;
    case "read":
      return `read: ${input.path}`;
    case "write":
      return `write: ${input.path}`;
    case "edit":
      return `edit: ${input.path}`;
    case "grep":
      return `grep: ${input.pattern} in ${input.path || "."}`;
    case "find":
      return `find: ${input.path || "."}`;
    case "ls":
      return `ls: ${input.path || "."}`;
    default:
      return `${toolName}: ${JSON.stringify(input).slice(0, 200)}`;
  }
}
