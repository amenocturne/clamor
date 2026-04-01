/**
 * Disguise — Pi Extension
 *
 * Unified agent identity system replacing model-router, context-loader,
 * workspace-context, and agent-teams. Each disguise defines a persona with
 * optional model override, tool restrictions, context injection rules, and
 * subagents. The user switches disguises via /disguise.
 *
 * Config: `.pi/disguise.yaml` or `disguise.yaml` at workspace root.
 */

import type { ExtensionAPI, ExtensionContext } from "@mariozechner/pi-coding-agent";
import { Text } from "@mariozechner/pi-tui";
import { Type } from "@sinclair/typebox";
import { existsSync, readFileSync, readdirSync } from "fs";
import { dirname, join, resolve } from "path";
import { parse } from "yaml";
import { spawnAgent, generateTaskId, type TaskInfo } from "../../lib/task-manager.ts";

// ── Types ───────────────────────────────────────────────────────────────

interface ContextRule {
  on: string;
  tool?: string;
  match?: string;
  inject: string | string[];
}

interface ToolRestrictions {
  deny?: string[];
  allow?: string[];
}

interface DisguiseNode {
  model?: string;
  tools?: ToolRestrictions;
  context_rules?: ContextRule[];
  subagents?: Record<string, DisguiseNode>;
}

interface DisguiseConfig {
  disguises: Record<string, DisguiseNode>;
}

// ── State ───────────────────────────────────────────────────────────────

let config: DisguiseConfig | null = null;
let activeDisguiseName: string | null = null;
let activeDisguise: DisguiseNode | null = null;
const injectedFiles = new Set<string>();
let piDir = "";
let workspaceContext = "";
let originalTools: string[] = [];

// ── Glob Matching ───────────────────────────────────────────────────────

function globMatch(pattern: string, text: string): boolean {
  const escaped = pattern
    .replace(/([.+^${}()|[\]\\])/g, "\\$1")
    .replace(/\*/g, ".*")
    .replace(/\?/g, ".");
  return new RegExp("^" + escaped + "$").test(text);
}

// ── File Search ─────────────────────────────────────────────────────────

function findFileUpward(startDir: string, filename: string, maxLevels = 5): string | null {
  let dir = resolve(startDir);
  for (let i = 0; i < maxLevels; i++) {
    const candidate = join(dir, filename);
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

// ── Config Loading ──────────────────────────────────────────────────────

function loadDisguiseConfig(): DisguiseConfig | null {
  const cwd = process.cwd();

  // Try .pi/disguise.yaml first
  const piPath = join(cwd, ".pi", "disguise.yaml");
  if (existsSync(piPath)) {
    piDir = join(cwd, ".pi");
    return parseDisguiseFile(piPath);
  }

  // Search upward for disguise.yaml at workspace root
  const found = findFileUpward(cwd, "disguise.yaml");
  if (found) {
    piDir = join(dirname(found), ".pi");
    return parseDisguiseFile(found);
  }

  return null;
}

function parseDisguiseFile(path: string): DisguiseConfig | null {
  try {
    const raw = readFileSync(path, "utf-8");
    const parsed = parse(raw);
    if (parsed?.disguises && typeof parsed.disguises === "object") {
      return parsed as DisguiseConfig;
    }
    return null;
  } catch {
    return null;
  }
}

// ── WORKSPACE.yaml ──────────────────────────────────────────────────────

function loadWorkspaceContext(): string {
  const cwd = process.cwd();
  const yamlPath = findFileUpward(cwd, "WORKSPACE.yaml");
  if (!yamlPath) return "";

  try {
    const raw = readFileSync(yamlPath, "utf-8");
    const workspace = parse(raw);
    return condenseWorkspace(workspace);
  } catch {
    return "";
  }
}

function condenseWorkspace(workspace: Record<string, any>): string {
  const projects = workspace.projects;
  if (!projects || typeof projects !== "object") return "";

  const lines: string[] = [];
  for (const [name, cfg] of Object.entries(projects) as [string, any][]) {
    const tech = Array.isArray(cfg.tech) ? cfg.tech.join(", ") : "";
    const explore = Array.isArray(cfg.explore_when) && cfg.explore_when.length > 0
      ? ` explore:[${cfg.explore_when.join(", ")}]`
      : "";
    lines.push(`- ${name}: ${cfg.path || "."} [${tech}]${explore}`);
  }
  return lines.join("\n");
}

// ── Context Injection Engine ────────────────────────────────────────────

function normalizeInject(inject: string | string[]): string[] {
  return Array.isArray(inject) ? inject : [inject];
}

function readContextFile(filePath: string): string | null {
  const resolved = resolve(piDir, filePath);
  if (!existsSync(resolved)) return null;
  try {
    return readFileSync(resolved, "utf-8");
  } catch {
    return null;
  }
}

function injectContextFiles(pi: ExtensionAPI, files: string[]): void {
  for (const file of files) {
    if (injectedFiles.has(file)) continue;

    const content = readContextFile(file);
    if (!content) continue;

    injectedFiles.add(file);
    pi.sendMessage({
      customType: "context-injection",
      content: `[Context: ${file}]\n\n${content}`,
      display: false,
    });
  }
}

function collectContextFilesForPrompt(files: string[]): string {
  const parts: string[] = [];
  for (const file of files) {
    if (injectedFiles.has(file)) continue;

    const content = readContextFile(file);
    if (!content) continue;

    injectedFiles.add(file);
    parts.push(`## ${file}\n\n${content}`);
  }
  return parts.join("\n\n");
}

// ── Rule Firing ─────────────────────────────────────────────────────────

function getRulesForEvent(node: DisguiseNode, eventType: string): ContextRule[] {
  if (!node.context_rules) return [];
  return node.context_rules.filter((r) => r.on === eventType);
}

function fireRules(pi: ExtensionAPI, node: DisguiseNode, eventType: string): void {
  const rules = getRulesForEvent(node, eventType);
  for (const rule of rules) {
    injectContextFiles(pi, normalizeInject(rule.inject));
  }
}

function collectRulesForPrompt(node: DisguiseNode, eventType: string): string {
  const rules = getRulesForEvent(node, eventType);
  const allFiles = rules.flatMap((r) => normalizeInject(r.inject));
  return collectContextFilesForPrompt(allFiles);
}

// ── Tool Call Argument Extraction ───────────────────────────────────────

function extractToolArg(toolName: string, input: Record<string, unknown>): string | null {
  if (["read", "write", "edit"].includes(toolName)) {
    return (input.file_path ?? input.path ?? null) as string | null;
  }
  if (toolName === "bash" || toolName === "bg-run") {
    return (input.command ?? null) as string | null;
  }
  if (toolName === "grep") {
    return (input.pattern ?? null) as string | null;
  }
  if (toolName === "find" || toolName === "glob") {
    return (input.path ?? input.pattern ?? null) as string | null;
  }
  return null;
}

// ── Tool Restrictions ───────────────────────────────────────────────────

function applyToolRestrictions(pi: ExtensionAPI, restrictions: ToolRestrictions | undefined): void {
  if (!restrictions) return;

  let tools = pi.getActiveTools();

  if (restrictions.allow) {
    const allowed = new Set(restrictions.allow);
    tools = tools.filter((t) => allowed.has(t));
  }

  if (restrictions.deny) {
    const denied = new Set(restrictions.deny);
    tools = tools.filter((t) => !denied.has(t));
  }

  if (restrictions.allow && restrictions.deny) {
    pi.appendEntry("warn: both allow and deny set in tool restrictions — deny wins on conflicts");
  }

  pi.setActiveTools(tools);
}

// ── Subagent Dispatch ───────────────────────────────────────────────────

function getExtensionsForSubagent(): string[] {
  const extDir = join(process.cwd(), ".pi", "extensions");
  const selfNames = new Set(["background-tasks", "agent-teams", "disguise"]);
  if (!existsSync(extDir)) return [];

  const paths: string[] = [];
  for (const entry of readdirSync(extDir)) {
    if (selfNames.has(entry)) continue;
    const full = resolve(extDir, entry);
    if (existsSync(join(full, "index.ts")) || existsSync(join(full, "package.json"))) {
      paths.push(full);
    }
  }
  return paths;
}

function buildSubagentPrompt(name: string, node: DisguiseNode, task: string): string {
  const parts: string[] = [`You are the "${name}" subagent.`];

  // Inject context rule files inline
  if (node.context_rules) {
    for (const rule of node.context_rules) {
      const files = normalizeInject(rule.inject);
      for (const file of files) {
        const content = readContextFile(file);
        if (content) parts.push(content);
      }
    }
  }

  parts.push("", `# Task\n${task}`);

  if (node.subagents) {
    const subNames = Object.keys(node.subagents);
    parts.push("", `# Your Subagents\nYou have subagents: ${subNames.join(", ")}. Delegate subtasks via bg-dispatch.`);
  }

  return parts.join("\n");
}

function resolveModel(node: DisguiseNode, ctx: ExtensionContext): string {
  if (node.model) return node.model;
  return ctx.model ? `${ctx.model.provider}/${ctx.model.id}` : "";
}

async function spawnSubagentWorker(task: string, model: string): Promise<TaskInfo> {
  const id = generateTaskId();
  return spawnAgent(id, task, model, process.cwd(), getExtensionsForSubagent(), "silent");
}

function waitForTask(info: TaskInfo, timeoutMs = 600_000): Promise<TaskInfo> {
  return new Promise((resolve) => {
    const start = Date.now();
    const check = setInterval(() => {
      if (info.status !== "running" && info.status !== "waiting") {
        clearInterval(check);
        resolve(info);
      } else if (Date.now() - start > timeoutMs) {
        clearInterval(check);
        info.status = "failed" as any;
        info.output += "\n[timed out after 10 minutes]";
        resolve(info);
      }
    }, 500);
  });
}

function getResult(info: TaskInfo): string {
  if (info.type === "agent" && info.finalReport) return info.finalReport;
  return info.output || "(no output)";
}

async function dispatchSubagents(
  task: string,
  parentNode: DisguiseNode,
  ctx: ExtensionContext,
): Promise<string> {
  if (!parentNode.subagents) return "(no subagents configured)";

  const entries = Object.entries(parentNode.subagents);
  const spawned: Array<{ name: string; info: TaskInfo }> = [];

  for (const [name, node] of entries) {
    const model = resolveModel(node, ctx);
    const prompt = buildSubagentPrompt(name, node, task);
    const info = await spawnSubagentWorker(prompt, model);
    spawned.push({ name, info });
  }

  const results = await Promise.all(
    spawned.map(async ({ name, info }) => ({
      name,
      result: await waitForTask(info),
    })),
  );

  return results.map(({ name, result }) =>
    `## ${name} [${result.status}]\n\n${getResult(result)}`,
  ).join("\n\n---\n\n");
}

// ── Extension Entry ─────────────────────────────────────────────────────

export default function (pi: ExtensionAPI) {

  // ── session_start ───────────────────────────────────────────────────

  pi.on("session_start", async (_event, ctx) => {
    // Load workspace context
    workspaceContext = loadWorkspaceContext();

    // Load disguise config
    config = loadDisguiseConfig();
    if (!config || Object.keys(config.disguises).length === 0) {
      ctx.ui.setStatus("disguise: none", "disguise");
      return;
    }

    // Activate the first disguise
    const names = Object.keys(config.disguises);
    activeDisguiseName = names[0];
    activeDisguise = config.disguises[activeDisguiseName];

    ctx.ui.setStatus(`disguise: ${activeDisguiseName}`, "disguise");

    // Save original tool set before any restrictions
    originalTools = pi.getActiveTools();

    // Apply tool restrictions
    applyToolRestrictions(pi, activeDisguise.tools);

    // Register bg-dispatch tool if active disguise has subagents
    if (activeDisguise.subagents && Object.keys(activeDisguise.subagents).length > 0) {
      registerDispatchTool(pi);
    }
  });

  // ── before_agent_start ──────────────────────────────────────────────

  pi.on("before_agent_start", async () => {
    const parts: string[] = [];

    // Workspace context (replaces workspace-context extension)
    if (workspaceContext) {
      parts.push(
        "## Workspace Projects\n\n" +
        "Available projects in this workspace (name: path [tech] explore_when):\n\n" +
        workspaceContext,
      );
    }

    // Active disguise info
    if (activeDisguiseName && activeDisguise) {
      parts.push(`## Active Disguise: ${activeDisguiseName}`);

      if (activeDisguise.subagents) {
        const subNames = Object.keys(activeDisguise.subagents);
        parts.push(`Subagents available: ${subNames.join(", ")}. Use bg-dispatch to delegate tasks.`);
      }

      // Collect session_start context rule files for system prompt
      const contextContent = collectRulesForPrompt(activeDisguise, "session_start");
      if (contextContent) parts.push(contextContent);
    }

    if (parts.length === 0) return {};
    return { appendSystemPrompt: parts.join("\n\n") };
  });

  // ── tool_call ───────────────────────────────────────────────────────

  pi.on("tool_call", async (event) => {
    if (!activeDisguise?.context_rules) return { block: false };

    const toolName = event.toolName;
    const input = event.input as Record<string, unknown>;
    const arg = extractToolArg(toolName, input);

    const rules = activeDisguise.context_rules.filter((r) => {
      if (r.on !== "tool_call") return false;
      if (r.tool && r.tool !== toolName) return false;
      if (r.match && arg && !globMatch(r.match, arg)) return false;
      if (r.match && !arg) return false;
      return true;
    });

    for (const rule of rules) {
      injectContextFiles(pi, normalizeInject(rule.inject));
    }

    return { block: false };
  });

  // ── agent_end ───────────────────────────────────────────────────────

  pi.on("agent_end", async () => {
    if (!activeDisguise) return;
    fireRules(pi, activeDisguise, "agent_end");
  });

  // ── session_compact ─────────────────────────────────────────────────

  pi.on("session_compact", async () => {
    // Fire context_compact rules
    if (activeDisguise) {
      fireRules(pi, activeDisguise, "context_compact");
    }

    // Resume directive (replaces workspace-context compaction handler)
    pi.sendMessage(
      {
        customType: "compaction-resume",
        content:
          "Context was compacted. Resume from where you left off. " +
          "Do not recap, do not re-read files mentioned in the summary, " +
          "do not ask where we were. If the summary mentions pending work, do that next." +
          (activeDisguiseName ? ` Active disguise: ${activeDisguiseName}.` : ""),
        display: false,
      },
      { deliverAs: "steer" },
    );
  });

  // ── /disguise command ───────────────────────────────────────────────

  pi.registerCommand("disguise", {
    description: "Switch between configured disguises",
    handler: async (_args, ctx) => {
      // Reload config in case it was edited
      config = loadDisguiseConfig();
      if (!config || Object.keys(config.disguises).length === 0) {
        ctx.ui.notify("No disguise.yaml found or no disguises defined.", "warning");
        return;
      }

      const names = Object.keys(config.disguises);
      const options = names.map((name) => {
        const node = config!.disguises[name];
        const parts: string[] = [name];
        if (node.model) parts.push(`model:${node.model}`);
        if (node.subagents) parts.push(`${Object.keys(node.subagents).length} subagents`);
        if (name === activeDisguiseName) parts.push("(active)");
        return parts.join(" | ");
      });

      const choice = await ctx.ui.select("Select disguise", options);
      if (choice === undefined) return;

      // Extract name from "name | model:... | ..." format
      const chosenName = choice.split(" | ")[0];
      const chosenNode = config.disguises[chosenName];
      if (!chosenNode) {
        ctx.ui.notify(`Disguise "${chosenName}" not found.`, "error");
        return;
      }

      // Clear injection tracking for the new disguise
      injectedFiles.clear();

      // Activate
      activeDisguiseName = chosenName;
      activeDisguise = chosenNode;
      ctx.ui.setStatus(`disguise: ${activeDisguiseName}`, "disguise");

      // Restore original tools before applying new restrictions
      if (originalTools.length > 0) {
        pi.setActiveTools(originalTools);
      }

      // Apply tool restrictions
      applyToolRestrictions(pi, activeDisguise.tools);

      // Register bg-dispatch if new disguise has subagents
      if (activeDisguise.subagents && Object.keys(activeDisguise.subagents).length > 0) {
        registerDispatchTool(pi);
      }

      // Fire session_start rules for the new disguise
      fireRules(pi, activeDisguise, "session_start");

      // Notify the agent about the switch
      pi.sendMessage({
        customType: "disguise-switch",
        content: `Disguise switched to "${activeDisguiseName}".` +
          (activeDisguise.subagents
            ? ` Subagents available: ${Object.keys(activeDisguise.subagents).join(", ")}.`
            : ""),
        display: true,
      });

      ctx.ui.notify(`Switched to disguise: ${chosenName}`, "info");
    },
  });
}

// ── bg-dispatch Tool Registration ───────────────────────────────────────

let dispatchToolRegistered = false;

function registerDispatchTool(pi: ExtensionAPI): void {
  if (dispatchToolRegistered) return;
  dispatchToolRegistered = true;

  pi.registerTool({
    name: "bg-dispatch",
    label: "Subagent Dispatch",
    description:
      "Dispatch a task to the active disguise's subagents. All subagents run " +
      "in parallel with their own model, tool restrictions, and context rules. " +
      "Returns aggregated results. Only available when the active disguise has subagents.",
    parameters: Type.Object({
      task: Type.String({ description: "Task for the subagents to perform" }),
      agents: Type.Optional(Type.Array(Type.String(), {
        description: "Specific subagent names to dispatch to (default: all)",
      })),
    }),

    async execute(_toolCallId, params, _signal, onUpdate, ctx) {
      if (!activeDisguise?.subagents) {
        return {
          content: [{ type: "text" as const, text: "No subagents configured for the active disguise." }],
        };
      }

      const targetAgents = params.agents
        ? Object.fromEntries(
            Object.entries(activeDisguise.subagents).filter(([name]) =>
              params.agents!.includes(name),
            ),
          )
        : activeDisguise.subagents;

      if (Object.keys(targetAgents).length === 0) {
        const available = Object.keys(activeDisguise.subagents).join(", ");
        return {
          content: [{ type: "text" as const, text: `None of the specified agents found. Available: ${available}` }],
        };
      }

      const agentNames = Object.keys(targetAgents);
      if (onUpdate) {
        onUpdate({
          content: [{ type: "text" as const, text: `Dispatching to ${agentNames.length} subagent(s): ${agentNames.join(", ")}...` }],
          details: { agents: agentNames, status: "running" },
        });
      }

      try {
        const parentWithTargets: DisguiseNode = {
          ...activeDisguise,
          subagents: targetAgents,
        };
        const result = await dispatchSubagents(params.task, parentWithTargets, ctx);
        const truncated = result.length > 8000 ? result.slice(-8000) + "\n... [truncated]" : result;

        return {
          content: [{ type: "text" as const, text: truncated }],
          details: { agents: agentNames, status: "done" },
        };
      } catch (err: any) {
        return {
          content: [{ type: "text" as const, text: `Subagent dispatch failed: ${err.message}` }],
          details: { agents: agentNames, status: "failed", error: err.message },
        };
      }
    },

    renderCall(args, theme) {
      const agentLabel = args.agents ? args.agents.join(", ") : "all";
      return new Text(
        theme.fg("toolTitle", theme.bold("bg-dispatch ")) +
          theme.fg("accent", agentLabel) +
          theme.fg("dim", ` — ${args.task?.slice(0, 50) ?? ""}`),
        0, 0,
      );
    },

    renderResult(result, _options, theme) {
      const details = result.details as { agents?: string[]; status?: string } | undefined;
      const icon = details?.status === "done" ? "+" : "x";
      const color = details?.status === "done" ? "success" : "error";
      return new Text(
        theme.fg(color, `${icon} `) +
          theme.fg("accent", details?.agents?.join(", ") ?? "dispatch") +
          theme.fg("dim", ` ${details?.status ?? "unknown"}`),
        0, 0,
      );
    },
  });
}
