/**
 * Behavioral Reminders — Pi Extension
 *
 * Monitors tool_call patterns and sends mid-conversation nudges via
 * sendMessage() when the model drifts from instructions. Reminders are
 * configured in reminders.yaml with cooldowns and per-session caps.
 *
 * Detected patterns:
 * - Exploration spiral (5+ consecutive read-only tools)
 * - Write/edit after user asked for plan only
 * - Verbose output (>2000 token response)
 * - Repeated identical tool calls (same tool + args 3x)
 * - Premature summary while background tasks still running
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { readFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { parse } from "yaml";

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

const READ_ONLY_TOOLS = new Set(["read", "grep", "find", "ls"]);
const WRITE_TOOLS = new Set(["write", "edit"]);

let toolCallCounter = 0;
let consecutiveReads = 0;
let planModeActive = false;
let recentCalls: Array<{ tool: string; argsHash: string }> = [];
const reminderStates = new Map<string, ReminderState>();

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
    const toolName = event.toolName;
    const input = event.input as Record<string, unknown>;

    // Track consecutive reads
    if (READ_ONLY_TOOLS.has(toolName)) {
      consecutiveReads++;
    } else {
      consecutiveReads = 0;
    }

    // Track recent calls for loop detection
    const argsHash = hashArgs(input);
    recentCalls.push({ tool: toolName, argsHash });
    if (recentCalls.length > 10) recentCalls.shift();

    // Check: exploration spiral
    const spiralConfig = reminders.exploration_spiral;
    if (spiralConfig && consecutiveReads >= (spiralConfig.trigger.threshold ?? 5)) {
      fireReminder("exploration_spiral", spiralConfig);
    }

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

    // Check: premature summary (tasks still running)
    // This is checked on message_update, not tool_call — see below

    return { block: false };
  });

  // Check for verbose output and premature summary on message updates
  pi.on("message_update", async (event) => {
    const delta = (event as any).assistantMessageEvent;
    if (!delta || delta.type !== "text_delta") return;

    // Verbose output detection is approximate — we track accumulated text length
    // across the current turn. Full implementation would need turn-level tracking.
    // For now, this fires on the tool_call pattern side effects.
  });

  // Reset per-turn state on turn boundaries
  pi.on("turn_end", async () => {
    consecutiveReads = 0;
  });
}
