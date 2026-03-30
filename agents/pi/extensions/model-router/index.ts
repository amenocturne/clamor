/**
 * Model Router — Pi Extension
 *
 * Reads `modelRouter` config from settings.json and exposes a
 * `getModelForRole(role)` function for other extensions to import.
 * This enables different agent roles (orchestrator, worker, reviewer)
 * to use different models.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { existsSync, readFileSync } from "fs";
import { join } from "path";

export type ModelRole = "orchestrator" | "lead" | "worker" | "reviewer" | "default";

let routerConfig: Record<string, string> = {};

export function loadConfig(): void {
  const settingsPath = join(process.cwd(), ".pi", "settings.json");
  if (!existsSync(settingsPath)) return;
  try {
    const settings = JSON.parse(readFileSync(settingsPath, "utf-8"));
    if (settings.modelRouter && typeof settings.modelRouter === "object") {
      routerConfig = settings.modelRouter;
    }
  } catch {}
}

export function getModelForRole(role: string): string {
  return routerConfig[role] ?? routerConfig["default"] ?? "";
}

export default function (pi: ExtensionAPI) {
  pi.on("session_start", async () => {
    loadConfig();
  });
}
