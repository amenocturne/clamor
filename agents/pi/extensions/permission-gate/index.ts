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
import { existsSync } from "fs";
import { resolve } from "path";
import { loadHookConfig, findMatchingHooks } from "./config.ts";
import type { HookConfig } from "./config.ts";
import { runHook } from "./hook-runner.ts";
import { writeRequest, waitForResponse, type PermissionRequest } from "../../lib/permission-queue.ts";

/** Tools that only read — safe to auto-allow within project dir */
const READ_ONLY_TOOLS = new Set(["read", "grep", "find", "ls"]);

/** Tools that modify files — also safe within project dir */
const FILE_TOOLS = new Set(["read", "write", "edit", "grep", "find", "ls"]);

/** Extension-registered tools that handle their own permissions — skip the gate */
const PASSTHROUGH_TOOLS = new Set([
  "bg-run", "bg-agent", "bg-status", "bg-result", "bg-kill",
]);

// ── Harness Enforcement State ────────────────────────────────────────────

/** Paths the model has read this session — required before editing */
const readPaths = new Set<string>();

/** Hashes of tool calls that returned errors — cleared each turn */
const failedCallHashes = new Set<string>();

/** Whether plan mode is active — blocks write/edit/bash/bg-run */
let planModeActive = false;

/** Tool names blocked during plan mode */
const PLAN_MODE_BLOCKED = new Set(["write", "edit", "bash", "bg-run"]);

/** Compute a stable hash key for a tool call */
function callHashKey(toolName: string, input: Record<string, unknown>): string {
  return toolName + ":" + JSON.stringify(input, Object.keys(input).sort());
}

// ── Tool Call Repair ─────────────────────────────────────────────────────

/**
 * Maps commonly hallucinated tool names to their correct equivalents.
 * Applied after case normalization (all keys are lowercase).
 */
const TOOL_NAME_ALIASES: Record<string, string> = {
  // shell/exec → bash (or bg-run if bash is replaced)
  shell: "bash",
  terminal: "bash",
  exec: "bash",
  execute: "bash",
  run_command: "bash",
  run: "bash",
  command: "bash",
  // search variants → grep
  search: "grep",
  find_files: "grep",
  ripgrep: "grep",
  rg: "grep",
  // glob-like
  glob: "find",
  list_files: "find",
  // read variants
  file_read: "read",
  readfile: "read",
  read_file: "read",
  cat: "read",
  view: "read",
  open: "read",
  // write variants
  file_write: "write",
  writefile: "write",
  write_file: "write",
  create_file: "write",
  save: "write",
  // edit variants
  file_edit: "edit",
  editfile: "edit",
  edit_file: "edit",
  patch: "edit",
  replace: "edit",
  modify: "edit",
};

/**
 * Required parameters per built-in tool, used for malformed input feedback.
 */
const TOOL_REQUIRED_PARAMS: Record<string, string[]> = {
  bash: ["command"],
  "bg-run": ["command"],
  read: ["path"],
  write: ["path", "content"],
  edit: ["path", "old_string", "new_string"],
  grep: ["pattern"],
  find: ["pattern"],
  ls: [],
};

/**
 * Normalize a tool name: lowercase + alias resolution.
 * When bash has been replaced by bg-run (background-tasks extension),
 * shell-like aliases resolve to bg-run instead.
 */
function normalizeToolName(raw: string, activeTools: Set<string>): string {
  const lower = raw.toLowerCase().trim();
  const mapped = TOOL_NAME_ALIASES[lower] ?? lower;

  // If the alias resolved to "bash" but bash isn't available and bg-run is,
  // redirect to bg-run. This handles the background-tasks replacement.
  if (mapped === "bash" && !activeTools.has("bash") && activeTools.has("bg-run")) {
    return "bg-run";
  }

  return mapped;
}

/**
 * Check if tool input is missing required parameters.
 * Returns a list of missing param names, or empty array if OK.
 */
function findMissingParams(toolName: string, input: Record<string, unknown>): string[] {
  const required = TOOL_REQUIRED_PARAMS[toolName];
  if (!required) return [];
  return required.filter((p) => input[p] === undefined || input[p] === null);
}

/**
 * Attempt tool call repair. Returns a block result if the call should be
 * rejected with feedback, or null if the call is valid and should proceed
 * through normal permission logic.
 *
 * Repair strategy — since Pi's event object is read-only, we can't silently
 * rewrite tool names. Instead we block and return actionable error messages
 * that tell the model exactly what to call instead.
 */
function repairToolCall(
  pi: ExtensionAPI,
  event: { toolName: string; input: unknown },
  ctx: { abort: () => void },
): { block: true; reason: string } | null {
  const raw = event.toolName;
  const activeTools = new Set(pi.getActiveTools());
  const normalized = normalizeToolName(raw, activeTools);
  const input = (event.input ?? {}) as Record<string, unknown>;
  const toolExists = activeTools.has(raw);

  // Tool name is wrong — either hallucinated, wrong case, or alias
  if (!toolExists) {
    if (activeTools.has(normalized)) {
      // We know the correct name — tell the model to retry with it
      logInterception(pi, raw, input, "repair", `"${raw}" → "${normalized}"`);
      ctx.abort();
      return {
        block: true,
        reason:
          `Tool "${raw}" does not exist. You meant "${normalized}". ` +
          `Call the "${normalized}" tool with the same arguments.`,
      };
    }

    // No match even after normalization — list available tools
    const available = [...activeTools].sort().join(", ");
    logInterception(pi, raw, input, "repair", `unknown tool "${raw}"`);
    ctx.abort();
    return {
      block: true,
      reason:
        `Tool "${raw}" does not exist. ` +
        `Available tools: ${available}. ` +
        `Pick the correct tool and try again.`,
    };
  }

  // Tool exists — check for malformed input (missing required params)
  const missing = findMissingParams(raw, input);
  if (missing.length > 0) {
    const allRequired = TOOL_REQUIRED_PARAMS[raw] ?? [];
    logInterception(pi, raw, input, "repair", `missing params: ${missing.join(", ")}`);
    ctx.abort();
    return {
      block: true,
      reason:
        `Invalid input for "${raw}". ` +
        `Missing required parameter${missing.length > 1 ? "s" : ""}: ${missing.join(", ")}. ` +
        `Expected parameters: ${allRequired.join(", ")}. ` +
        `Try again with the correct parameters.`,
    };
  }

  return null;
}

/**
 * Try to import enqueuePermission from the sibling background-tasks extension.
 * This is the unified permission queue that processes prompts one at a time.
 * Falls back to direct ctx.ui.confirm() if background-tasks isn't loaded.
 */
let enqueuePermission: ((toolName: string, toolInput: Record<string, unknown>) => Promise<"allow" | "deny">) | null = null;

try {
  const qw = await import("../../lib/queue-watcher.ts");
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
    // Tool call repair — normalize names and catch hallucinations before
    // anything else runs. Must happen before permission hooks since hooks
    // match on tool names.
    const repairResult = repairToolCall(pi, event, ctx);
    if (repairResult) return repairResult;

    const input = event.input as Record<string, unknown>;

    // ── Harness Enforcement (after repair, before hooks) ──────────────

    // 1. Read-before-edit: block write/edit on files the model hasn't read
    if (event.toolName === "edit" || event.toolName === "write") {
      const filePath = (input.path ?? input.file_path ?? "") as string;
      if (filePath) {
        const resolved = resolve(cwd, filePath);
        const fileExists = existsSync(resolved);
        if (fileExists && !readPaths.has(resolved)) {
          logInterception(pi, event.toolName, input, "enforce", "read-before-edit");
          ctx.abort();
          return {
            block: true,
            reason:
              `You must read a file before editing it. Call the read tool on '${filePath}' first.`,
          };
        }
      }
    }

    // Track reads — add paths to the read set
    if (event.toolName === "read") {
      const filePath = (input.path ?? input.file_path ?? "") as string;
      if (filePath) {
        readPaths.add(resolve(cwd, filePath));
      }
    }
    if (event.toolName === "grep") {
      const grepPath = (input.path ?? input.file_path ?? "") as string;
      if (grepPath) {
        readPaths.add(resolve(cwd, grepPath));
      }
    }

    // 2. No-retry-same-failed-call: block identical retries
    const hash = callHashKey(event.toolName, input);
    if (failedCallHashes.has(hash)) {
      logInterception(pi, event.toolName, input, "enforce", "retry-same-failed-call");
      ctx.abort();
      return {
        block: true,
        reason:
          "This exact tool call already failed. Read the error message and try a different approach.",
      };
    }

    // 3. Plan mode tool gating: block write tools when plan mode is active
    if (planModeActive && PLAN_MODE_BLOCKED.has(event.toolName)) {
      logInterception(pi, event.toolName, input, "enforce", "plan-mode-blocked");
      ctx.abort();
      return {
        block: true,
        reason:
          "Plan mode is active — write tools are disabled. Propose changes in text instead. " +
          'Say "go ahead" or "implement it" to exit plan mode.',
      };
    }

    // ── End Harness Enforcement ───────────────────────────────────────

    // Extension tools that manage their own permissions — don't gate them
    if (PASSTHROUGH_TOOLS.has(event.toolName)) {
      return { block: false };
    }

    const hooks = findMatchingHooks(config, event.toolName);

    // Run matching hooks sequentially — deny takes priority
    for (const hook of hooks) {
      const result = await runHook(hook, event.toolName, input, cwd);

      if (result.decision === "deny") {
        failedCallHashes.add(hash);
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
          failedCallHashes.add(hash);
          ctx.abort();
          const summary = formatToolSummary(event.toolName, input);
          return { block: true, reason: `The user denied permission for: ${summary}\n\nDo not retry this operation unless the user explicitly asks.` };
        }
        return { block: false };
      }
      const promptResult = await promptUser(pi, ctx, event.toolName, input);
      if (promptResult.block) failedCallHashes.add(hash);
      return promptResult;
    }

    // Non-interactive (subagent): delegate to file-based permission queue
    if (taskId) {
      const reqResult = await requestPermission(pi, ctx, taskId, event.toolName, input);
      if (reqResult.block) failedCallHashes.add(hash);
      return reqResult;
    }

    // No hooks, not interactive, no task ID — block by default
    failedCallHashes.add(hash);
    logInterception(pi, event.toolName, input, "deny", "No permission source available");
    ctx.abort();
    return {
      block: true,
      reason: "Permission denied: no hooks matched and no interactive session or task ID available",
    };
  });

  // ── Plan Mode Detection ─────────────────────────────────────────────

  /** All tools before plan mode was activated — used to restore */
  let preplanTools: string[] | null = null;

  pi.on("input", async (event) => {
    const text = typeof event === "string" ? event : (event as any).text ?? "";
    const lower = text.toLowerCase();

    const wantsPlan =
      lower.includes("just plan") ||
      lower.includes("plan only") ||
      lower.includes("don't implement") ||
      lower.includes("do not implement") ||
      lower.includes("only plan");

    const wantsImplement =
      lower.includes("go ahead") ||
      lower.includes("proceed") ||
      lower.includes("implement it") ||
      lower.includes("implement this") ||
      lower.includes("do it");

    if (wantsPlan && !planModeActive) {
      planModeActive = true;
      preplanTools = pi.getActiveTools();
      const readOnly = preplanTools.filter((t) => !PLAN_MODE_BLOCKED.has(t));
      pi.setActiveTools(readOnly);
      pi.sendMessage({
        customType: "enforcement",
        content: "Plan mode active. Write tools disabled. Propose changes in text.",
        display: true,
      });
      pi.appendEntry("permission-gate-log", {
        event: "plan-mode-on",
        removedTools: [...PLAN_MODE_BLOCKED].filter((t) => preplanTools!.includes(t)),
      });
    }

    if (wantsImplement && planModeActive) {
      planModeActive = false;
      if (preplanTools) {
        pi.setActiveTools(preplanTools);
        preplanTools = null;
      }
      pi.sendMessage({
        customType: "enforcement",
        content: "Plan mode deactivated. You may now write code.",
        display: true,
      });
      pi.appendEntry("permission-gate-log", { event: "plan-mode-off" });
    }

    return { action: "continue" as const };
  });

  // ── Turn End: reset per-turn enforcement state ──────────────────────

  pi.on("turn_end", async () => {
    failedCallHashes.clear();
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
  return { block: true, reason: `The user denied permission for: ${summary}\n\nDo not retry this operation unless the user explicitly asks.` };
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

  const summary = formatToolSummary(toolName, input);
  logInterception(pi, toolName, input, "deny", response.reason || "denied via queue");
  ctx.abort();
  return { block: true, reason: `The user denied permission for: ${summary}\n\nDo not retry this operation unless the user explicitly asks.` };
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
