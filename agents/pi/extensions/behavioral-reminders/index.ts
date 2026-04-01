/**
 * Behavioral Reminders — Pi Extension
 *
 * Monitors tool_call patterns and sends mid-conversation nudges via
 * sendMessage() when the model drifts from instructions. Reminders are
 * configured in reminders.yaml with cooldowns and per-session caps.
 *
 * Detected patterns:
 * - Write/edit after user asked for plan only
 * - Verbose output (>2000 token response, ~8000 chars)
 * - Repeated identical tool calls (same tool + args 3x)
 * - Premature summary while background tasks still running
 * - Multi-tool attempt (2+ tool calls in one turn)
 * - Content echoing (repeating large chunks of read output)
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { parse } from "yaml";
import { getAllTasks } from "../../lib/task-manager.ts";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── Types ───────────────────────────────────────────────────────────────

interface ReminderConfig {
  trigger: { type: string; threshold?: number; tools?: string[] };
  message: string;
  cooldown: number;
  max_per_session: number;
}

interface ReminderState {
  lastFiredAt: number; // tool call counter when last fired
  totalFired: number;
}

// ── Tracking State ──────────────────────────────────────────────────────

const WRITE_TOOLS = new Set(["write", "edit"]);

let toolCallCounter = 0;
let planModeActive = false;
let recentCalls: Array<{ tool: string; argsHash: string }> = [];
const reminderStates = new Map<string, ReminderState>();

// Per-turn text accumulator for verbose output and content echoing
let turnTextBuffer = "";
let turnToolCallCount = 0;

// Last read tool result for content echoing detection
let lastReadResult = "";

// ── Config Loading ──────────────────────────────────────────────────────

function loadReminders(): Record<string, ReminderConfig> {
  try {
    const raw = readFileSync(join(__dirname, "reminders.yaml"), "utf-8");
    const config = parse(raw);
    return config?.reminders ?? {};
  } catch {
    return {};
  }
}

// ── Helpers ─────────────────────────────────────────────────────────────

function hashArgs(input: Record<string, unknown>): string {
  return JSON.stringify(input, Object.keys(input).sort());
}

function canFire(name: string, config: ReminderConfig): boolean {
  const state = reminderStates.get(name) ?? { lastFiredAt: -999, totalFired: 0 };
  if (state.totalFired >= config.max_per_session) return false;
  if (toolCallCounter - state.lastFiredAt < config.cooldown) return false;
  return true;
}

function recordFire(name: string): void {
  const state = reminderStates.get(name) ?? { lastFiredAt: 0, totalFired: 0 };
  state.lastFiredAt = toolCallCounter;
  state.totalFired++;
  reminderStates.set(name, state);
}

function runningBgTaskCount(): number {
  try {
    return getAllTasks().filter((t) => t.status === "running").length;
  } catch {
    return 0;
  }
}

// ── Extension Entry ─────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  const reminders = loadReminders();

  function fireReminder(name: string, config: ReminderConfig): void {
    if (!canFire(name, config)) return;
    recordFire(name);
    pi.sendMessage(
      { customType: "behavioral-reminder", content: config.message.trim(), display: true },
    );
  }

  // Detect plan mode from user input
  pi.on("input", async (event) => {
    const text = typeof event === "string" ? event : (event as any).text ?? "";
    const lower = text.toLowerCase();
    if (
      lower.includes("just plan") ||
      lower.includes("plan only") ||
      lower.includes("don't implement") ||
      lower.includes("do not implement") ||
      lower.includes("only plan")
    ) {
      planModeActive = true;
    }
    if (
      lower.includes("go ahead") ||
      lower.includes("proceed") ||
      lower.includes("implement it") ||
      lower.includes("implement this")
    ) {
      planModeActive = false;
    }
    return { action: "continue" as const };
  });

  pi.on("tool_call", async (event) => {
    toolCallCounter++;
    turnToolCallCount++;
    const toolName = event.toolName;
    const input = event.input as Record<string, unknown>;

    // Track recent calls for loop detection
    const argsHash = hashArgs(input);
    recentCalls.push({ tool: toolName, argsHash });
    if (recentCalls.length > 10) recentCalls.shift();

    // Check: write after plan-only
    const planConfig = reminders.write_after_plan_only;
    if (planConfig && planModeActive && WRITE_TOOLS.has(toolName)) {
      fireReminder("write_after_plan_only", planConfig);
    }

    // Check: repeated identical tool calls
    const repeatConfig = reminders.repeated_tool_call;
    if (repeatConfig) {
      const threshold = repeatConfig.trigger.threshold ?? 3;
      const recent = recentCalls.slice(-threshold);
      if (
        recent.length >= threshold &&
        recent.every((c) => c.tool === recent[0].tool && c.argsHash === recent[0].argsHash)
      ) {
        fireReminder("repeated_tool_call", repeatConfig);
      }
    }

    // Check: multi-tool attempt (2+ tool calls in same turn)
    const multiConfig = reminders.multi_tool_attempt;
    if (multiConfig && turnToolCallCount >= 2) {
      fireReminder("multi_tool_attempt", multiConfig);
    }

    // When a read tool completes, stash its input for content echoing detection.
    // We capture the file_path from the tool input — the actual content comes via
    // message_update when the model responds. We store the read args so we know
    // the next text output should be checked.
    if (toolName === "read" && input.file_path) {
      // Read the file ourselves to get the content for comparison.
      // This is lightweight since the file was just read by the tool.
      try {
        const content = readFileSync(String(input.file_path), "utf-8");
        lastReadResult = content;
      } catch {
        lastReadResult = "";
      }
    }

    return { block: false };
  });

  // Track text output for verbose_output, premature_summary, and content_echoing
  pi.on("message_update", async (event) => {
    const delta = (event as any).assistantMessageEvent;
    if (!delta || delta.type !== "text_delta") return;

    const text = typeof delta.delta === "string" ? delta.delta : "";
    turnTextBuffer += text;

    // Check: verbose output (~4 chars per token, threshold in tokens from config)
    const verboseConfig = reminders.verbose_output;
    if (verboseConfig) {
      const charThreshold = (verboseConfig.trigger.threshold ?? 2000) * 4;
      if (turnTextBuffer.length >= charThreshold) {
        fireReminder("verbose_output", verboseConfig);
      }
    }

    // Check: premature summary (model outputs text while bg tasks are running)
    const summaryConfig = reminders.premature_summary;
    if (summaryConfig && runningBgTaskCount() > 0 && turnTextBuffer.length > 100) {
      fireReminder("premature_summary", summaryConfig);
    }

    // Check: content echoing (model repeats large chunks of last read result)
    const echoConfig = reminders.content_echoing;
    if (echoConfig && lastReadResult.length > 0 && turnTextBuffer.length > 500) {
      const overlap = countOverlap(turnTextBuffer, lastReadResult);
      if (overlap > 500) {
        fireReminder("content_echoing", echoConfig);
        // Clear to avoid re-firing on subsequent deltas in the same turn
        lastReadResult = "";
      }
    }

  });

  // Reset per-turn state on turn boundaries
  pi.on("turn_end", async () => {
    turnTextBuffer = "";
    turnToolCallCount = 0;
  });
}

// ── Content Echoing Helpers ─────────────────────────────────────────────

/**
 * Estimate character overlap between model output and read content.
 * Uses a sliding window approach: checks if consecutive chunks of the model
 * output appear verbatim in the read content. Returns total matched chars.
 */
function countOverlap(modelText: string, readContent: string): number {
  const CHUNK_SIZE = 50;
  if (modelText.length < CHUNK_SIZE || readContent.length < CHUNK_SIZE) return 0;

  let matched = 0;
  for (let i = 0; i <= modelText.length - CHUNK_SIZE; i += CHUNK_SIZE) {
    const chunk = modelText.slice(i, i + CHUNK_SIZE);
    if (readContent.includes(chunk)) {
      matched += CHUNK_SIZE;
    }
  }
  return matched;
}
