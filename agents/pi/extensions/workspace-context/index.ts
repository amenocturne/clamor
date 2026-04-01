/**
 * Workspace Context — Pi Extension
 *
 * Finds WORKSPACE.yaml in the cwd or parent directories, reads it, and injects
 * a condensed project index into the system prompt. This gives the agent awareness
 * of all projects in the workspace without manual reading.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { existsSync, readFileSync } from "fs";
import { dirname, join, resolve } from "path";
import { parse } from "yaml";

function findWorkspaceYaml(startDir: string, maxLevels = 5): string | null {
  let dir = resolve(startDir);
  for (let i = 0; i < maxLevels; i++) {
    const candidate = join(dir, "WORKSPACE.yaml");
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return null;
}

function condense(workspace: Record<string, any>): string {
  const projects = workspace.projects;
  if (!projects || typeof projects !== "object") return "";

  const lines: string[] = [];
  for (const [name, config] of Object.entries(projects) as [string, any][]) {
    const tech = Array.isArray(config.tech) ? config.tech.join(", ") : "";
    const explore = Array.isArray(config.explore_when) && config.explore_when.length > 0
      ? ` explore:[${config.explore_when.join(", ")}]`
      : "";
    lines.push(`- ${name}: ${config.path || "."} [${tech}]${explore}`);
  }
  return lines.join("\n");
}

export default function (pi: ExtensionAPI) {
  pi.on("before_agent_start", async () => {
    const yamlPath = findWorkspaceYaml(process.cwd());
    if (!yamlPath) return {};

    try {
      const raw = readFileSync(yamlPath, "utf-8");
      const workspace = parse(raw);
      const condensed = condense(workspace);
      if (!condensed) return {};

      return {
        appendSystemPrompt:
          "## Workspace Projects\n\n" +
          "Available projects in this workspace (name: path [tech] explore_when):\n\n" +
          condensed,
      };
    } catch {
      return {};
    }
  });

  // After context compaction, remind the agent to resume without recap.
  // Pi fires session_compact when older messages are summarized to free tokens.
  pi.on("session_compact", async () => {
    pi.sendMessage(
      {
        customType: "compaction-resume",
        content:
          "Context was compacted. Resume from where you left off. " +
          "Do not recap, do not re-read files mentioned in the summary, " +
          "do not ask where we were. If the summary mentions pending work, do that next.",
        display: false,
      },
      { deliverAs: "steer" },
    );
  });
}
