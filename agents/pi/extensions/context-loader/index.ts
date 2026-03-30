/**
 * Context Loader — Pi Extension
 *
 * Detects what the agent is working on (docs, testing, planning, reviewing, config)
 * by inspecting tool_call events (file paths, commands). When the context changes,
 * sends a focused reminder via sendMessage() with relevant instruction files.
 *
 * General instructions are injected once at session start via appendSystemPrompt.
 * Context-specific instructions are injected on context switches with debouncing.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { existsSync, readFileSync } from "fs";
import { basename, dirname, extname, join, resolve } from "path";
import { fileURLToPath } from "url";
import { parse } from "yaml";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ── Types ───────────────────────────────────────────────────────────────

interface DetectRule {
  file_extensions?: string[];
  directories?: string[];
  commands?: string[];
  keywords?: string[];
}

interface ContextDef {
  detect: DetectRule;
  instructions: Array<{ path: string }>;
}

interface ProjectOverride {
  path: string;
  instructions?: Array<{ path: string }>;
  contexts?: Record<string, { instructions: Array<{ path: string }> }>;
}

interface LoaderConfig {
  general: Array<{ path: string }>;
  contexts: Record<string, ContextDef>;
  projects?: Record<string, ProjectOverride>;
}

// ── State ───────────────────────────────────────────────────────────────

let currentContext: string | null = null;
let toolCallsSinceLastSwitch = 0;
const DEBOUNCE_CALLS = 10;

// ── Config Loading ──────────────────────────────────────────────────────

function loadConfig(): LoaderConfig {
  const configPath = join(__dirname, "config.yaml");
  try {
    const raw = readFileSync(configPath, "utf-8");
    const parsed = parse(raw);
    return {
      general: parsed?.general ?? [],
      contexts: parsed?.contexts ?? {},
      projects: parsed?.projects,
    };
  } catch {
    return { general: [], contexts: {} };
  }
}

function loadInstructionFile(instrPath: string): string | null {
  // Resolve relative to agentic-kit repo root
  const agenticKitJson = join(process.cwd(), ".pi", "agentic-kit.json");
  let repoRoot = dirname(__dirname); // fallback: up from extension dir
  try {
    if (existsSync(agenticKitJson)) {
      const config = JSON.parse(readFileSync(agenticKitJson, "utf-8"));
      if (config.agentic_kit) repoRoot = config.agentic_kit;
    }
  } catch {}

  const fullPath = resolve(repoRoot, instrPath);
  if (!existsSync(fullPath)) return null;
  try {
    return readFileSync(fullPath, "utf-8");
  } catch {
    return null;
  }
}

// ── Detection Logic ─────────────────────────────────────────────────────

function extractFilePath(toolName: string, input: Record<string, unknown>): string | null {
  if (["read", "write", "edit"].includes(toolName)) {
    return (input.file_path ?? input.path ?? null) as string | null;
  }
  if (["grep", "find"].includes(toolName)) {
    return (input.path ?? null) as string | null;
  }
  return null;
}

function extractCommand(toolName: string, input: Record<string, unknown>): string | null {
  if (toolName === "bash" || toolName === "bg-run") {
    return (input.command ?? null) as string | null;
  }
  return null;
}

function detectContext(
  toolName: string,
  input: Record<string, unknown>,
  contexts: Record<string, ContextDef>,
): string | null {
  const filePath = extractFilePath(toolName, input);
  const command = extractCommand(toolName, input);

  for (const [name, def] of Object.entries(contexts)) {
    const rule = def.detect;

    // Check file extensions
    if (filePath && rule.file_extensions) {
      const ext = extname(filePath);
      const base = basename(filePath);
      for (const pattern of rule.file_extensions) {
        // Handle patterns like "test_*.py" or ".test.ts"
        if (pattern.includes("*")) {
          const regex = new RegExp("^" + pattern.replace(/\*/g, ".*") + "$");
          if (regex.test(base)) return name;
        } else if (base.endsWith(pattern) || ext === pattern) {
          return name;
        }
      }
    }

    // Check directories
    if (filePath && rule.directories) {
      for (const dir of rule.directories) {
        if (filePath.includes(dir)) return name;
      }
    }

    // Check commands
    if (command && rule.commands) {
      const cmdLower = command.toLowerCase();
      for (const cmd of rule.commands) {
        if (cmdLower.includes(cmd.toLowerCase())) return name;
      }
    }
  }

  return null;
}

// ── Instruction Assembly ────────────────────────────────────────────────

function assembleInstructions(
  contextName: string,
  config: LoaderConfig,
): string {
  const contextDef = config.contexts[contextName];
  if (!contextDef) return "";

  const parts: string[] = [];

  // Load context-specific instructions
  for (const instr of contextDef.instructions) {
    const content = loadInstructionFile(instr.path);
    if (content) parts.push(content);
  }

  // Check project overrides
  if (config.projects) {
    const cwd = process.cwd();
    for (const [, project] of Object.entries(config.projects)) {
      if (!cwd.startsWith(project.path)) continue;
      const override = project.contexts?.[contextName];
      if (override?.instructions) {
        for (const instr of override.instructions) {
          const content = loadInstructionFile(instr.path);
          if (content) parts.push(content);
        }
      }
    }
  }

  return parts.join("\n\n");
}

// ── Extension Entry ─────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {
  const config = loadConfig();

  // Inject general instructions at session start
  pi.on("before_agent_start", async () => {
    if (config.general.length === 0) return {};

    const parts: string[] = [];
    for (const instr of config.general) {
      const content = loadInstructionFile(instr.path);
      if (content) parts.push(content);
    }

    if (parts.length === 0) return {};
    return { appendSystemPrompt: parts.join("\n\n") };
  });

  // Detect context from tool calls
  pi.on("tool_call", async (event) => {
    toolCallsSinceLastSwitch++;
    const input = event.input as Record<string, unknown>;

    const detected = detectContext(event.toolName, input, config.contexts);
    if (!detected) return { block: false };

    // Same context — no switch needed
    if (detected === currentContext) return { block: false };

    // Debounce: don't re-fire within N tool calls of last switch
    if (toolCallsSinceLastSwitch < DEBOUNCE_CALLS) return { block: false };

    // Context switch detected
    currentContext = detected;
    toolCallsSinceLastSwitch = 0;

    const instructions = assembleInstructions(detected, config);
    if (!instructions) return { block: false };

    pi.sendMessage({
      customType: "context-switch",
      content: `[Context: ${detected}]\n\n${instructions}`,
      display: true,
    });

    return { block: false };
  });
}
