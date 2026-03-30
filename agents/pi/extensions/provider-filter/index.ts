/**
 * Provider Filter — Pi Extension
 *
 * Hides unwanted built-in providers from the model picker by registering
 * dummy providers with empty model lists. Only providers listed in
 * `allowedProviders` in settings.json remain visible.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { existsSync, readFileSync } from "fs";
import { join } from "path";

const KNOWN_BUILTINS = [
  "anthropic", "openai", "google", "groq",
  "openrouter", "local", "deepseek", "mistral", "xai",
];

function readAllowedProviders(): string[] | null {
  const settingsPath = join(process.cwd(), ".pi", "settings.json");
  if (!existsSync(settingsPath)) return null;
  try {
    const settings = JSON.parse(readFileSync(settingsPath, "utf-8"));
    return Array.isArray(settings.allowedProviders) ? settings.allowedProviders : null;
  } catch {
    return null;
  }
}

export default function (pi: ExtensionAPI) {
  pi.on("session_start", async () => {
    const allowed = readAllowedProviders();
    if (!allowed) return;

    const allowSet = new Set(allowed.map((p: string) => p.toLowerCase()));

    for (const name of KNOWN_BUILTINS) {
      if (allowSet.has(name)) continue;
      pi.registerProvider(name, {
        baseUrl: "",
        apiKey: "",
        api: "openai-completions",
        models: [],
      });
    }
  });
}
