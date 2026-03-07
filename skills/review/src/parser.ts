import type { DiffLine, DiffLineType, FileDiff, Hunk } from "./types.ts";

const EXTENSION_MAP: Record<string, string> = {
	".ts": "typescript",
	".tsx": "typescript",
	".js": "javascript",
	".jsx": "javascript",
	".py": "python",
	".rs": "rust",
	".go": "go",
	".hs": "haskell",
	".java": "java",
	".rb": "ruby",
	".css": "css",
	".html": "html",
	".json": "json",
	".md": "markdown",
	".yaml": "yaml",
	".yml": "yaml",
	".toml": "toml",
	".sh": "bash",
	".sql": "sql",
	".c": "c",
	".cpp": "cpp",
	".h": "c",
	".hpp": "cpp",
	".swift": "swift",
	".kt": "kotlin",
	".scala": "scala",
	".ex": "elixir",
	".exs": "elixir",
	".zig": "zig",
};

const MAX_LINES = 10000;
const TRUNCATION_CONTEXT = 500;

export const detectLanguage = (filePath: string): string => {
	const dot = filePath.lastIndexOf(".");
	if (dot === -1) return "plaintext";
	const ext = filePath.slice(dot);
	return EXTENSION_MAP[ext] ?? "plaintext";
};

const extractPath = (line: string, prefix: string): string | null => {
	if (!line.startsWith(prefix)) return null;
	const rest = line.slice(prefix.length);
	if (rest === "/dev/null") return null;
	// strip leading a/ or b/
	return rest.replace(/^[ab]\//, "");
};

const parseHunkHeader = (
	line: string,
): { oldStart: number; newStart: number } | null => {
	const match = line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
	if (!match) return null;
	return { oldStart: Number(match[1]), newStart: Number(match[2]) };
};

const classifyLine = (
	raw: string,
): { type: DiffLineType; content: string } | null => {
	if (raw.startsWith("\\ No newline")) return null;
	if (raw.startsWith("+")) return { type: "add", content: raw.slice(1) };
	if (raw.startsWith("-")) return { type: "delete", content: raw.slice(1) };
	// context line — strip leading space
	return { type: "context", content: raw.startsWith(" ") ? raw.slice(1) : raw };
};

const parseHunks = (bodyLines: readonly string[]): readonly Hunk[] => {
	const hunks: Hunk[] = [];
	let currentHunk: { oldStart: number; newStart: number; lines: DiffLine[] } | null = null;
	let oldNum = 0;
	let newNum = 0;

	// Drop trailing empty string from split("\n")
	const lines =
		bodyLines.length > 0 && bodyLines[bodyLines.length - 1] === ""
			? bodyLines.slice(0, -1)
			: bodyLines;

	for (const raw of lines) {
		const header = parseHunkHeader(raw);
		if (header) {
			if (currentHunk) hunks.push(currentHunk);
			currentHunk = { oldStart: header.oldStart, newStart: header.newStart, lines: [] };
			oldNum = header.oldStart;
			newNum = header.newStart;
			continue;
		}
		if (!currentHunk) continue;

		const classified = classifyLine(raw);
		if (!classified) continue;

		const { type, content } = classified;
		let line: DiffLine;
		if (type === "add") {
			line = { type, oldNum: null, newNum, content };
			newNum++;
		} else if (type === "delete") {
			line = { type, oldNum, newNum: null, content };
			oldNum++;
		} else {
			line = { type, oldNum, newNum, content };
			oldNum++;
			newNum++;
		}
		currentHunk.lines.push(line);
	}
	if (currentHunk) hunks.push(currentHunk);
	return hunks;
};

const truncateHunks = (hunks: readonly Hunk[]): readonly Hunk[] => {
	// Collect all changed line indices per hunk so we can build a keep-set
	const allLines: { hunkIdx: number; lineIdx: number; changed: boolean }[] = [];
	for (let hi = 0; hi < hunks.length; hi++) {
		const h = hunks[hi]!;
		for (let li = 0; li < h.lines.length; li++) {
			const l = h.lines[li]!;
			allLines.push({ hunkIdx: hi, lineIdx: li, changed: l.type !== "context" });
		}
	}

	// Mark which global indices to keep (within TRUNCATION_CONTEXT of a change)
	const keep = new Set<number>();
	for (let i = 0; i < allLines.length; i++) {
		if (allLines[i]!.changed) {
			const lo = Math.max(0, i - TRUNCATION_CONTEXT);
			const hi = Math.min(allLines.length - 1, i + TRUNCATION_CONTEXT);
			for (let j = lo; j <= hi; j++) keep.add(j);
		}
	}

	// Rebuild hunks keeping only marked lines
	const result: Hunk[] = [];
	let globalIdx = 0;
	for (const hunk of hunks) {
		const keptLines: DiffLine[] = [];
		for (let li = 0; li < hunk.lines.length; li++) {
			if (keep.has(globalIdx)) {
				keptLines.push(hunk.lines[li]!);
			}
			globalIdx++;
		}
		if (keptLines.length > 0) {
			result.push({ oldStart: hunk.oldStart, newStart: hunk.newStart, lines: keptLines });
		}
	}
	return result;
};

const parseGitHeaderPaths = (
	headerLine: string,
): { gitOld: string; gitNew: string } | null => {
	// Header line is the remainder after "diff --git ", e.g. "a/foo.ts b/foo.ts"
	// Handle paths with spaces by finding the " b/" separator
	const sepIdx = headerLine.indexOf(" b/");
	if (sepIdx === -1) return null;
	const gitOld = headerLine.slice(0, sepIdx).replace(/^a\//, "");
	const gitNew = headerLine.slice(sepIdx + 1).replace(/^b\//, "");
	return { gitOld, gitNew };
};

const parseFileSection = (section: string): FileDiff | null => {
	const lines = section.split("\n");

	// Extract fallback paths from the "diff --git a/X b/Y" header
	const gitHeader = parseGitHeaderPaths(lines[0] ?? "");

	let oldPath: string | null = null;
	let newPath: string | null = null;
	let renameFrom: string | null = null;
	let renameTo: string | null = null;
	let binary = false;
	let bodyStart = -1;

	for (let i = 0; i < lines.length; i++) {
		const line = lines[i]!;
		if (line.startsWith("--- ")) {
			oldPath = extractPath(line, "--- ");
		} else if (line.startsWith("+++ ")) {
			newPath = extractPath(line, "+++ ");
		} else if (line.startsWith("rename from ")) {
			renameFrom = line.slice("rename from ".length);
		} else if (line.startsWith("rename to ")) {
			renameTo = line.slice("rename to ".length);
		} else if (line.startsWith("Binary files")) {
			binary = true;
		} else if (line.startsWith("@@")) {
			bodyStart = i;
			break;
		}
	}

	// Determine the file path, falling back to git header paths
	const path = newPath ?? renameTo ?? oldPath ?? gitHeader?.gitNew ?? null;
	if (!path && !binary) return null;
	const finalPath = path ?? "(binary)";

	// Detect rename
	const isRename =
		(renameFrom != null && renameTo != null && renameFrom !== renameTo) ||
		(oldPath != null && newPath != null && oldPath !== newPath);
	const finalOldPath = isRename ? (renameFrom ?? oldPath ?? undefined) : undefined;

	if (binary) {
		return {
			path: finalPath,
			...(finalOldPath ? { oldPath: finalOldPath } : {}),
			language: detectLanguage(finalPath),
			binary: true,
			truncated: false,
			hunks: [],
		};
	}

	const bodyLines = bodyStart >= 0 ? lines.slice(bodyStart) : [];
	let hunks = parseHunks(bodyLines);

	// Count total lines
	let totalLines = 0;
	for (const h of hunks) totalLines += h.lines.length;

	let truncated = false;
	if (totalLines > MAX_LINES) {
		hunks = truncateHunks(hunks);
		truncated = true;
	}

	return {
		path: finalPath,
		...(finalOldPath ? { oldPath: finalOldPath } : {}),
		language: detectLanguage(finalPath),
		binary: false,
		truncated,
		hunks,
	};
};

export const textToFileDiff = (content: string, filePath: string): FileDiff => {
	const rawLines = content.split("\n");
	// Drop trailing empty line from split (matches how text editors show line count)
	const lines: readonly DiffLine[] = rawLines.map((line, i) => ({
		type: "context" as const,
		oldNum: i + 1,
		newNum: i + 1,
		content: line,
	}));
	const hunk: Hunk = { oldStart: 1, newStart: 1, lines };
	return {
		path: filePath,
		language: detectLanguage(filePath),
		binary: false,
		truncated: false,
		hunks: [hunk],
	};
};

export const parseDiff = (rawDiff: string): FileDiff[] => {
	if (!rawDiff.trim()) return [];

	// Split on "diff --git" markers; first element is empty/preamble
	const sections = rawDiff.split(/^diff --git /m);
	const results: FileDiff[] = [];

	for (let i = 1; i < sections.length; i++) {
		const parsed = parseFileSection(sections[i]!);
		if (parsed) results.push(parsed);
	}

	return results;
};
