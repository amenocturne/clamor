/**
 * Hook Configuration — Reads and parses .pi/hooks.json
 *
 * Loads the hook config from the project root, resolves {hook_dir} placeholders,
 * and provides matching logic to find relevant hooks for a given tool name.
 * Uses the same hooks.json format as Claude Code.
 */

import { existsSync, readFileSync } from "fs";
import { dirname, join } from "path";

export interface HookEntry {
  type: "command";
  command: string;
  timeout: number;
}

export interface MatcherGroup {
  matcher: string;
  hooks: HookEntry[];
}

export interface HookConfig {
  PreToolUse?: MatcherGroup[];
}

/**
 * Load hook configuration from .pi/hooks.json in the given working directory.
 * Resolves {hook_dir} placeholders in command paths to the directory containing hooks.json.
 * Returns an empty config if the file is missing or malformed.
 */
export function loadHookConfig(cwd: string): HookConfig {
  const hooksPath = join(cwd, ".pi", "hooks.json");
  if (!existsSync(hooksPath)) return {};

  try {
    const hookDir = dirname(hooksPath);
    const raw = readFileSync(hooksPath, "utf-8").replaceAll("{hook_dir}", hookDir);
    const parsed = JSON.parse(raw);

    if (typeof parsed !== "object" || parsed === null) return {};

    return parsed as HookConfig;
  } catch {
    return {};
  }
}

/**
 * Find all hooks that match a given tool name.
 * The matcher field is a pipe-separated list of tool names (case-insensitive).
 * Pi uses lowercase tool names (bash, read, write) but matchers may be capitalized (Bash, Read).
 */
export function findMatchingHooks(config: HookConfig, toolName: string): HookEntry[] {
  const groups = config.PreToolUse;
  if (!groups || groups.length === 0) return [];

  const normalizedTool = toolName.toLowerCase();
  const matched: HookEntry[] = [];

  for (const group of groups) {
    const matchers = group.matcher.split("|").map((m) => m.toLowerCase());
    if (matchers.includes(normalizedTool)) {
      matched.push(...group.hooks);
    }
  }

  return matched;
}
