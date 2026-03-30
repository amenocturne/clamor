/**
 * Model Router — Pi Extension
 *
 * Thin wrapper that loads model-router config on session_start.
 * Core logic lives in lib/model-router.ts.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { loadConfig } from "../../lib/model-router.ts";

// Re-export for any extension that imports from this path
export { getModelForRole, loadConfig, type ModelRole } from "../../lib/model-router.ts";

export default function (pi: ExtensionAPI) {
  pi.on("session_start", async () => {
    loadConfig();
  });
}
