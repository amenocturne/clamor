/**
 * Nestor DP Auth Provider Extension for Pi
 *
 * Connects Pi to Tinkoff's internal LLM API via DP (DevPlatform) authentication.
 * The Nestor API is OpenAI-compatible, so we delegate streaming to Pi's built-in
 * OpenAI Completions implementation with a custom Nestor-Token header.
 *
 * Usage:
 *   pi -e ./path/to/pi-nestor-provider
 *   /login nestor          # triggers DP auth (browser SSO)
 *
 *   # Or if you already have a DP session:
 *   pi -e ./path/to/pi-nestor-provider --provider nestor
 */

import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import {
	type Api,
	type AssistantMessageEventStream,
	type Context,
	createAssistantMessageEventStream,
	type Model,
	type OAuthCredentials,
	type OAuthLoginCallbacks,
	type SimpleStreamOptions,
	streamSimpleOpenAICompletions,
} from "@mariozechner/pi-ai";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

// =============================================================================
// Constants
// =============================================================================

const NESTOR_BASE = "https://code-completion-nestor.tcsbank.ru";
const API_BASE = `${NESTOR_BASE}/api/v1/cli/openai-like/v1`;
const TOKEN_ENDPOINT = `${NESTOR_BASE}/api/v2/token`;
const MODELS_ENDPOINT = `${NESTOR_BASE}/api/v1/cli/models`;

const DP_WORKDIR_NAME = "dp_v13.4.2";

// =============================================================================
// DP Binary
// =============================================================================

function findDpBinary(): string {
	const candidates = [
		"/usr/local/bin/dp",
		join(homedir(), ".nessy", DP_WORKDIR_NAME, "dp"),
	];

	for (const p of candidates) {
		if (existsSync(p)) return p;
	}

	// Fall back to PATH
	try {
		const found = execFileSync("which", ["dp"], { stdio: "pipe" }).toString().trim();
		if (found) return found;
	} catch {}

	throw new Error(
		"dp binary not found. Expected at /usr/local/bin/dp or ~/.nessy/dp_v13.4.2/dp",
	);
}

function dpEnv(): Record<string, string> {
	const env = { ...process.env as Record<string, string> };

	// Only set DP_WORKDIR if the nessy-managed directory exists.
	// System-installed dp (/usr/local/bin/dp) uses its own default workdir
	// and forcing a nonexistent path breaks auth state lookup.
	const nessyWorkdir = join(homedir(), ".nessy", DP_WORKDIR_NAME);
	if (existsSync(nessyWorkdir)) {
		env.DP_WORKDIR = nessyWorkdir;
	}

	return env;
}

// =============================================================================
// Token Management
// =============================================================================

function getDpToken(dpPath: string): string {
	let raw: string;
	let stderr = "";
	try {
		const result = execFileSync(dpPath, ["auth", "print-token"], {
			stdio: ["ignore", "pipe", "pipe"],
			timeout: 5_000,
			env: dpEnv(),
		});
		raw = result.toString().trim();
	} catch (e: any) {
		// dp exits non-zero when not logged in, with the error on stderr
		stderr = e?.stderr?.toString?.() ?? "";
		raw = e?.stdout?.toString?.()?.trim() ?? "";
	}

	// Not logged in: dp writes "no access token found..." to stderr
	// and may also output error text to stdout
	if (
		!raw ||
		raw.includes("no access token") ||
		raw.includes("authorize") ||
		stderr.includes("no access token") ||
		raw.length < 10  // valid tokens are always long
	) {
		throw new Error("not-logged-in");
	}
	return raw;
}

async function exchangeForJwt(dpToken: string): Promise<{ jwt: string; expiresAt: number }> {
	const res = await fetch(TOKEN_ENDPOINT, {
		method: "POST",
		headers: {
			"Content-Type": "application/json",
			Authorization: `Bearer ${dpToken}`,
			"X-Request-Id": crypto.randomUUID(),
		},
		body: "{}",
	});

	if (!res.ok) {
		const body = await res.text();
		throw new Error(
			`Token exchange failed (${res.status}): ${body || "(empty response)"}\n` +
			`Endpoint: ${TOKEN_ENDPOINT}\n` +
			`DP token prefix: ${dpToken.substring(0, 20)}...`,
		);
	}

	const data = (await res.json()) as {
		jwt: string;
		token: { expires_at: string };
	};

	return {
		jwt: data.jwt,
		expiresAt: new Date(data.token.expires_at).getTime(),
	};
}

// =============================================================================
// Model Discovery
// =============================================================================

interface NestorModel {
	name: string;
	desc?: string;
	is_default?: boolean;
}

async function fetchNestorModels(jwt: string): Promise<NestorModel[]> {
	const res = await fetch(MODELS_ENDPOINT, {
		headers: { "Content-Type": "application/json", "Nestor-Token": jwt },
	});

	if (!res.ok) return [];

	const data = await res.json();
	return Array.isArray(data) ? data : (data as { models?: NestorModel[] }).models ?? [];
}

// =============================================================================
// OAuth Integration
// =============================================================================

let dpPath: string | undefined;
let piRef: ExtensionAPI | undefined;

async function login(callbacks: OAuthLoginCallbacks): Promise<OAuthCredentials> {
	dpPath = findDpBinary();

	// Try existing DP session first
	try {
		const dpToken = getDpToken(dpPath);
		const { jwt, expiresAt } = await exchangeForJwt(dpToken);
		await updateModels(jwt);
		return { refresh: "dp-session", access: jwt, expires: expiresAt };
	} catch (e) {
		// Only fall through to interactive login if not logged in.
		// Propagate real errors (network, malformed response, etc.)
		if (!(e instanceof Error) || e.message !== "not-logged-in") {
			throw e;
		}
	}

	// dp auth login needs a real TTY to open the browser, which conflicts
	// with Pi's TUI. Ask the user to run it in another terminal.
	await callbacks.onPrompt({
		message:
			"No active DP session. Run this in another terminal:\n\n" +
			"    dp auth login\n\n" +
			"Complete the browser login, then press Enter here.",
	});

	// Retry after user says they've logged in
	let dpToken: string;
	try {
		dpToken = getDpToken(dpPath);
	} catch {
		throw new Error(
			"Still no valid DP session. Make sure 'dp auth login' completed successfully.",
		);
	}

	const { jwt, expiresAt } = await exchangeForJwt(dpToken);
	await updateModels(jwt);

	return { refresh: "dp-session", access: jwt, expires: expiresAt };
}

async function refreshToken(credentials: OAuthCredentials): Promise<OAuthCredentials> {
	dpPath = dpPath || findDpBinary();

	// The DP session persists independently — just get a fresh token
	const dpToken = getDpToken(dpPath);
	const { jwt, expiresAt } = await exchangeForJwt(dpToken);

	return { refresh: "dp-session", access: jwt, expires: expiresAt };
}

function getApiKey(credentials: OAuthCredentials): string {
	return credentials.access;
}

// =============================================================================
// Model Capability Inference
// =============================================================================

// The Nestor API doesn't return context window or max output tokens,
// so we infer from model name patterns.

function inferContextWindow(id: string): number {
	if (id.includes("qwen3") && id.includes("35")) return 1_048_576; // Qwen 3.5: 1M
	if (id.includes("qwen3")) return 131_072; // Qwen 3: 128k
	if (id.includes("qwen2.5")) return 131_072;
	if (id.includes("gpt-4o") || id.includes("gpt-4-o")) return 128_000;
	if (id.includes("gpt-oss")) return 128_000;
	if (id.includes("deepseek")) return 128_000;
	return 128_000; // safe default
}

function inferMaxTokens(id: string): number {
	if (id.includes("qwen3") && id.includes("35")) return 16_384;
	if (id.includes("qwen3")) return 8_192;
	if (id.includes("gpt")) return 4_096;
	return 8_192; // safe default
}

// =============================================================================
// Dynamic Model Registration
// =============================================================================

async function updateModels(jwt: string): Promise<void> {
	if (!piRef) return;

	const nestorModels = await fetchNestorModels(jwt);
	if (nestorModels.length === 0) return;

	piRef.registerProvider("nestor", {
		baseUrl: API_BASE,
		api: "openai-completions",
		models: nestorModels.map((m) => {
			const id = m.name.toLowerCase();
			const isQwen = id.includes("qwen");
			const isVision = id.includes("-vl") || id.includes("vision");
			const isReasoning = isQwen || id.includes("think") || id.includes("reason");

			// The Nestor API doesn't expose context window / max tokens per model,
			// so we infer from the model name. Defaults are conservative.
			const contextWindow = inferContextWindow(id);
			const maxTokens = inferMaxTokens(id);

			return {
				id: m.name,
				name: m.desc || m.name,
				reasoning: isReasoning,
				input: (isVision ? ["text", "image"] : ["text"]) as ("text" | "image")[],
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
				contextWindow,
				maxTokens,
				compat: {
					maxTokensField: "max_tokens" as const,
					supportsDeveloperRole: false,
					...(isQwen && { thinkingFormat: "qwen" as const }),
				},
			};
		}),
		oauth: { name: "Nestor (DP Auth)", login, refreshToken, getApiKey },
		streamSimple: streamNestor,
	});
}

// =============================================================================
// Think Tag Parser
// =============================================================================

// The Nestor API returns thinking as <think>...</think> tags inline in the
// content field instead of using a dedicated reasoning_content field.
// This interceptor converts those tags into proper thinking events that
// Pi renders as collapsible thinking blocks.

interface ThinkTagState {
	insideThink: boolean;
	buffer: string;
	thinkingContentIndex: number | null;
}

function createThinkTagInterceptor(output: { content: any[] }) {
	const state: ThinkTagState = {
		insideThink: false,
		buffer: "",
		thinkingContentIndex: null,
	};

	// Process a text delta, returning events to emit
	function processTextDelta(
		delta: string,
		contentIndex: number,
		partial: any,
	): Array<{ type: string; [key: string]: any }> {
		const events: Array<{ type: string; [key: string]: any }> = [];
		state.buffer += delta;

		while (state.buffer.length > 0) {
			if (!state.insideThink) {
				const openIdx = state.buffer.indexOf("<think>");
				if (openIdx === -1) {
					// No <think> tag — might be a partial tag at the end
					// Keep last 6 chars in buffer in case of partial "<think"
					const safeLen = Math.max(0, state.buffer.length - 6);
					if (safeLen > 0) {
						const text = state.buffer.substring(0, safeLen);
						state.buffer = state.buffer.substring(safeLen);
						if (text) {
							events.push({
								type: "text_delta",
								contentIndex,
								delta: text,
								partial,
							});
						}
					}
					break;
				}

				// Emit text before <think>
				if (openIdx > 0) {
					events.push({
						type: "text_delta",
						contentIndex,
						delta: state.buffer.substring(0, openIdx),
						partial,
					});
				}

				// Enter thinking mode
				state.insideThink = true;
				state.buffer = state.buffer.substring(openIdx + 7); // skip "<think>"

				// Start a thinking block
				const thinkBlock = { type: "thinking", thinking: "" };
				output.content.push(thinkBlock);
				state.thinkingContentIndex = output.content.length - 1;
				events.push({
					type: "thinking_start",
					contentIndex: state.thinkingContentIndex,
					partial,
				});
			} else {
				const closeIdx = state.buffer.indexOf("</think>");
				if (closeIdx === -1) {
					// No closing tag yet — might be partial
					const safeLen = Math.max(0, state.buffer.length - 8);
					if (safeLen > 0) {
						const text = state.buffer.substring(0, safeLen);
						state.buffer = state.buffer.substring(safeLen);
						if (text && state.thinkingContentIndex !== null) {
							const block = output.content[state.thinkingContentIndex];
							if (block?.type === "thinking") block.thinking += text;
							events.push({
								type: "thinking_delta",
								contentIndex: state.thinkingContentIndex,
								delta: text,
								partial,
							});
						}
					}
					break;
				}

				// Emit thinking before </think>
				if (closeIdx > 0 && state.thinkingContentIndex !== null) {
					const text = state.buffer.substring(0, closeIdx);
					const block = output.content[state.thinkingContentIndex];
					if (block?.type === "thinking") block.thinking += text;
					events.push({
						type: "thinking_delta",
						contentIndex: state.thinkingContentIndex,
						delta: text,
						partial,
					});
				}

				// End thinking block
				if (state.thinkingContentIndex !== null) {
					const block = output.content[state.thinkingContentIndex];
					events.push({
						type: "thinking_end",
						contentIndex: state.thinkingContentIndex,
						content: block?.type === "thinking" ? block.thinking : "",
						partial,
					});
				}

				state.insideThink = false;
				state.thinkingContentIndex = null;
				state.buffer = state.buffer.substring(closeIdx + 8); // skip "</think>"
			}
		}

		return events;
	}

	// Flush any remaining buffer
	function flush(contentIndex: number, partial: any): Array<{ type: string; [key: string]: any }> {
		const events: Array<{ type: string; [key: string]: any }> = [];
		if (state.buffer.length > 0) {
			if (state.insideThink && state.thinkingContentIndex !== null) {
				const block = output.content[state.thinkingContentIndex];
				if (block?.type === "thinking") block.thinking += state.buffer;
				events.push({
					type: "thinking_delta",
					contentIndex: state.thinkingContentIndex,
					delta: state.buffer,
					partial,
				});
				events.push({
					type: "thinking_end",
					contentIndex: state.thinkingContentIndex,
					content: block?.type === "thinking" ? block.thinking : "",
					partial,
				});
			} else {
				events.push({
					type: "text_delta",
					contentIndex,
					delta: state.buffer,
					partial,
				});
			}
			state.buffer = "";
		}
		return events;
	}

	return { processTextDelta, flush, state };
}

// =============================================================================
// Stream Function
// =============================================================================

function streamNestor(
	model: Model<Api>,
	context: Context,
	options?: SimpleStreamOptions,
): AssistantMessageEventStream {
	const stream = createAssistantMessageEventStream();

	(async () => {
		try {
			const jwt = options?.apiKey;
			if (!jwt) {
				throw new Error("Not authenticated. Run /login nestor");
			}

			const modelWithBaseUrl = { ...model, baseUrl: API_BASE };
			const innerStream = streamSimpleOpenAICompletions(
				modelWithBaseUrl as Model<"openai-completions">,
				context,
				{
					...options,
					apiKey: "nestor-dp-auth",
					headers: {
						...options?.headers,
						"Nestor-Token": jwt,
					},
				},
			);

			// Intercept the stream to parse <think> tags from content
			const outputRef = { content: [] as any[] };
			const interceptor = createThinkTagInterceptor(outputRef);

			for await (const event of innerStream) {
				// Track the output content array from the partial
				if ("partial" in event && event.partial?.content) {
					outputRef.content = event.partial.content;
				}

				// Intercept text deltas to parse <think> tags
				if (event.type === "text_delta" && "delta" in event && typeof event.delta === "string") {
					const events = interceptor.processTextDelta(
						event.delta,
						"contentIndex" in event ? (event as any).contentIndex : 0,
						"partial" in event ? event.partial : undefined,
					);
					for (const e of events) stream.push(e as any);
					continue;
				}

				// On stream end, flush any remaining buffered content
				if (event.type === "done" || event.type === "error") {
					const flushed = interceptor.flush(0, "partial" in event ? (event as any).partial : undefined);
					for (const e of flushed) stream.push(e as any);
				}

				// If it's a thinking event from the inner stream (reasoning_content),
				// pass it through — the API might support both formats
				stream.push(event);
			}
			stream.end();
		} catch (error) {
			stream.push({
				type: "error",
				reason: "error",
				error: {
					role: "assistant",
					content: [],
					api: model.api,
					provider: model.provider,
					model: model.id,
					usage: {
						input: 0,
						output: 0,
						cacheRead: 0,
						cacheWrite: 0,
						totalTokens: 0,
						cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
					},
					stopReason: "error",
					errorMessage: error instanceof Error ? error.message : String(error),
					timestamp: Date.now(),
				},
			});
			stream.end();
		}
	})();

	return stream;
}

// =============================================================================
// Extension Entry Point
// =============================================================================

export default function (pi: ExtensionAPI) {
	piRef = pi;

	// Register with a placeholder model — real models loaded after /login
	pi.registerProvider("nestor", {
		baseUrl: API_BASE,
		apiKey: "NESTOR_JWT",
		api: "openai-completions",
		models: [
			{
				id: "default",
				name: "Nestor Default (login to discover models)",
				reasoning: false,
				input: ["text"],
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
				contextWindow: 128_000,
				maxTokens: 4096,
				compat: {
					maxTokensField: "max_tokens",
					supportsDeveloperRole: false,
				},
			},
		],
		oauth: {
			name: "Nestor (DP Auth)",
			login,
			refreshToken,
			getApiKey,
		},
		streamSimple: streamNestor,
	});
}
