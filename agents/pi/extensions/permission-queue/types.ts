/**
 * Permission Queue — Shared Types
 *
 * Request/response schemas for file-based IPC between subagent
 * permission-gate (write side) and main session background-tasks (read side).
 */

export interface PermissionRequest {
  /** Unique request ID (nanoid or uuid) */
  id: string;
  /** Background task ID that owns this subagent */
  taskId: string;
  /** Pi tool name (bash, read, write, edit, grep, find, ls) */
  toolName: string;
  /** Tool input parameters */
  toolInput: Record<string, unknown>;
  /** ISO timestamp */
  createdAt: string;
}

export interface PermissionResponse {
  /** Must match the request ID */
  id: string;
  /** User's decision */
  decision: "allow" | "deny";
  /** Optional reason for denial */
  reason?: string;
  /** ISO timestamp */
  respondedAt: string;
}

/** Directory layout: ~/.pi/agent/permission-queue/<taskId>/<requestId>.request.json */
export const QUEUE_BASE_DIR = ".pi/agent/permission-queue";
