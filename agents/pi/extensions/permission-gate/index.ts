/**
 * Permission Gate — Pi extension for tool call interception
 *
 * Intercepts all tool calls, runs configured agentic-kit hooks (smart-approve,
 * deny-read, etc.) as subprocesses, and blocks/allows based on their output.
 * When no hook has an opinion and the session is interactive, prompts the user.
 * In non-interactive (subagent) mode, delegates to the permission queue for
 * the main session to handle.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { randomUUID } from "crypto";
import { loadHookConfig, findMatchingHooks } from "./config.ts";
import type { HookConfig } from "./config.ts";
import { runHook } from "./hook-runner.ts";
import { writeRequest, waitForResponse } from "../permission-queue/index.ts";
import type { PermissionRequest } from "../permission-queue/types.ts";

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

    // All hooks abstained or no hooks matched — fall through to user decision
    if (interactive) {
      return promptUser(pi, ctx, event.toolName, input);
    }

    // Non-interactive: delegate to permission queue
    if (taskId) {
      return requestPermission(pi, ctx, taskId, event.toolName, input);
    }

    // No hooks, not interactive, no task ID — block by default for safety
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
