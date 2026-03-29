/**
 * Hook Runner — Subprocess execution using the Claude Code hook protocol
 *
 * Spawns hook commands as subprocesses, pipes JSON via stdin/stdout, and
 * interprets the permission decision from hookSpecificOutput. Handles
 * timeouts, missing output, and non-zero exits gracefully.
 */

import { spawn } from "child_process";
import type { HookEntry } from "./config.ts";

export interface HookResult {
  decision: "allow" | "deny" | "abstain";
  reason?: string;
}

/** Map Pi lowercase tool names to capitalized names expected by hooks. */
const TOOL_NAME_MAP: Record<string, string> = {
  bash: "Bash",
  read: "Read",
  write: "Write",
  edit: "Edit",
  grep: "Grep",
  find: "Find",
  ls: "Ls",
};

function capitalizeToolName(piToolName: string): string {
  return TOOL_NAME_MAP[piToolName] ?? piToolName.charAt(0).toUpperCase() + piToolName.slice(1);
}

/**
 * Run a single hook command as a subprocess.
 *
 * Protocol:
 * - stdin: { tool_name, tool_input } as JSON
 * - stdout: { hookSpecificOutput: { permissionDecision, permissionDecisionReason? } } as JSON
 * - exit 0 with valid JSON = decision made
 * - exit 0 with no output = abstain
 * - non-zero exit = abstain
 */
export function runHook(
  hook: HookEntry,
  toolName: string,
  toolInput: Record<string, unknown>,
  cwd: string,
): Promise<HookResult> {
  return new Promise((resolve) => {
    const timeoutMs = (hook.timeout || 5) * 1000;

    const parts = hook.command.split(/\s+/);
    const cmd = parts[0];
    const args = parts.slice(1);

    let child: ReturnType<typeof spawn>;
    try {
      child = spawn(cmd, args, {
        cwd,
        stdio: ["pipe", "pipe", "pipe"],
        env: { ...process.env },
      });
    } catch {
      resolve({ decision: "abstain" });
      return;
    }

    let stdout = "";
    let settled = false;

    const finish = (result: HookResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };

    const timer = setTimeout(() => {
      if (!settled) {
        try {
          child.kill("SIGKILL");
        } catch {}
        finish({ decision: "abstain", reason: "hook timed out" });
      }
    }, timeoutMs);

    child.stdout!.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });

    child.on("error", () => {
      finish({ decision: "abstain" });
    });

    child.on("close", (code) => {
      if (code !== 0) {
        finish({ decision: "abstain" });
        return;
      }

      const trimmed = stdout.trim();
      if (!trimmed) {
        finish({ decision: "abstain" });
        return;
      }

      try {
        const parsed = JSON.parse(trimmed);
        const output = parsed?.hookSpecificOutput;
        if (!output || !output.permissionDecision) {
          finish({ decision: "abstain" });
          return;
        }

        const decision = output.permissionDecision;
        if (decision === "allow") {
          finish({ decision: "allow" });
        } else if (decision === "deny") {
          finish({
            decision: "deny",
            reason: output.permissionDecisionReason || "Denied by hook",
          });
        } else {
          finish({ decision: "abstain" });
        }
      } catch {
        finish({ decision: "abstain" });
      }
    });

    // Write the hook input to stdin and close it
    const input = JSON.stringify({
      tool_name: capitalizeToolName(toolName),
      tool_input: toolInput,
    });

    try {
      child.stdin!.write(input);
      child.stdin!.end();
    } catch {
      finish({ decision: "abstain" });
    }
  });
}
