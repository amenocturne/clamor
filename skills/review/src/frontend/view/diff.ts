import { h } from "snabbdom";
import type { VNode } from "snabbdom";
import hljs from "highlight.js";
import type { Model, Msg, FileDiff, Hunk, DiffLine, ContextExpansion } from "../../types.ts";
import { savedCommentView, commentBoxView } from "./comment.ts";

// Track whether we installed the global mouseup listener
let globalListenerInstalled = false;
let dispatchRef: ((msg: Msg) => void) | null = null;

const installGlobalListener = (dispatch: (msg: Msg) => void): void => {
	dispatchRef = dispatch;
	if (globalListenerInstalled) return;
	globalListenerInstalled = true;
	window.addEventListener("mouseup", () => {
		if (dispatchRef) dispatchRef({ type: "endDrag" });
	});
};

// --- Helpers ---

const fileChangeStats = (file: FileDiff): { added: number; deleted: number } => {
	let added = 0;
	let deleted = 0;
	for (const hunk of file.hunks) {
		for (const line of hunk.lines) {
			if (line.type === "add") added++;
			if (line.type === "delete") deleted++;
		}
	}
	return { added, deleted };
};

// Cache highlighted results — diff data never changes during a session
const highlightCache = new Map<string, readonly string[]>();

const highlightFile = (file: FileDiff, viewKey: string): readonly string[] => {
	const cacheKey = `${viewKey}:${file.path}`;
	const cached = highlightCache.get(cacheKey);
	if (cached) return cached;

	const allContent = file.hunks.flatMap((hunk) => hunk.lines.map((l) => l.content));
	const joined = allContent.join("\n");

	let highlighted: string;
	try {
		const result = hljs.highlight(joined, { language: file.language });
		highlighted = result.value;
	} catch {
		highlighted = joined.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
	}

	const lines = highlighted.split("\n");
	highlightCache.set(cacheKey, lines);
	return lines;
};

// Compute visible line indices for a hunk based on context expansion
const computeVisibleRange = (
	lines: readonly DiffLine[],
	expansion: ContextExpansion,
): { startVisible: number; endVisible: number } => {
	// Find first and last change line indices
	let firstChange = -1;
	let lastChange = -1;
	for (let i = 0; i < lines.length; i++) {
		if (lines[i]!.type !== "context") {
			if (firstChange === -1) firstChange = i;
			lastChange = i;
		}
	}

	// No changes in hunk — show all (pure context hunk)
	if (firstChange === -1) {
		return { startVisible: 0, endVisible: lines.length };
	}

	// Count leading context lines
	const leadingContext = firstChange;
	// Count trailing context lines
	const trailingContext = lines.length - 1 - lastChange;

	const startVisible = Math.max(0, leadingContext - expansion.above);
	const endVisible = Math.min(lines.length, lines.length - trailingContext + expansion.below);

	return { startVisible, endVisible };
};

// Check if a line is within the finalized comment draft range
const isLineSelected = (lineNum: number, model: Model, filePath: string): boolean => {
	const draft = model.commentDraft;
	if (!draft || draft.file !== filePath) return false;
	return lineNum >= draft.startLine && lineNum <= draft.endLine;
};

// Check if a line is within the active drag range (visual feedback only)
const isLineDragging = (lineNum: number, model: Model, filePath: string): boolean => {
	const drag = model.dragSelection;
	if (!drag || drag.file !== filePath) return false;
	const lo = Math.min(drag.startLine, drag.endLine);
	const hi = Math.max(drag.startLine, drag.endLine);
	return lineNum >= lo && lineNum <= hi;
};

// --- Line View ---

const lineContentCell = (highlighted: string): VNode =>
	h("td.line-content", {
		hook: {
			insert: (vnode) => {
				(vnode.elm as HTMLElement).innerHTML = highlighted;
			},
			update: (_, vnode) => {
				(vnode.elm as HTMLElement).innerHTML = highlighted;
			},
		},
	});

const lineView = (
	line: DiffLine,
	highlighted: string,
	file: FileDiff,
	fileIdx: number,
	model: Model,
	dispatch: (msg: Msg) => void,
): VNode => {
	installGlobalListener(dispatch);

	const lineClass =
		line.type === "add" ? "line-add" : line.type === "delete" ? "line-del" : "line-context";

	const lineNum = line.newNum;
	const hasNewNum = lineNum != null;

	// Determine selection CSS classes
	const selected = hasNewNum && isLineSelected(lineNum, model, file.path);
	const dragging = hasNewNum && isLineDragging(lineNum, model, file.path);

	// Row-level handlers — entire row is clickable for selection
	const rowHandlers: Record<string, (e: Event) => void> = {};

	if (hasNewNum) {
		rowHandlers.mousedown = (e: Event) => {
			e.preventDefault();
			dispatch({ type: "startDrag", file: file.path, startLine: lineNum });
		};

		rowHandlers.mouseenter = () => {
			if (model.dragSelection && model.dragSelection.file === file.path) {
				dispatch({ type: "updateDrag", endLine: lineNum });
			}
		};
	}

	return h(`tr.${lineClass}`, {
		key: `${file.path}:${line.oldNum}:${line.newNum}`,
		class: {
			"line-selected": selected,
			"line-selecting": dragging,
		},
		on: rowHandlers,
	}, [
		h("td.gutter", {
			class: { "gutter-del": line.type === "delete" },
			attrs: hasNewNum ? {
				role: "button",
				tabindex: "0",
				"aria-label": `Select line ${lineNum} for comment`,
			} : {},
		}, hasNewNum ? String(lineNum) : line.oldNum != null ? String(line.oldNum) : ""),
		lineContentCell(highlighted),
	]);
};

// --- Expand Arrows ---

const expandArrow = (key: string, direction: "above" | "below", dispatch: (msg: Msg) => void): VNode =>
	h("tr.expand-row", {
		key: `expand-${key}-${direction}`,
		attrs: {
			role: "button",
			tabindex: "0",
			"aria-label": direction === "above" ? "Show 20 more lines above" : "Show 20 more lines below",
		},
		on: {
			click: () => dispatch({ type: "expandContext", key, direction }),
			keydown: (e: KeyboardEvent) => {
				if (e.key === "Enter" || e.key === " ") {
					e.preventDefault();
					dispatch({ type: "expandContext", key, direction });
				}
			},
		},
	}, [
		h("td", { attrs: { colspan: 2 } }, direction === "above" ? "\u25B2 Show more" : "\u25BC Show more"),
	]);

// --- Hunk View ---

const hunkView = (
	hunk: Hunk,
	highlightedLines: readonly string[],
	lineOffset: number,
	file: FileDiff,
	fileIdx: number,
	hunkIdx: number,
	model: Model,
	dispatch: (msg: Msg) => void,
): VNode[] => {
	const key = `${fileIdx}-${hunkIdx}`;
	const expansion: ContextExpansion = model.contextExpansion[key] ?? { above: 3, below: 3 };
	const { startVisible, endVisible } = computeVisibleRange(hunk.lines, expansion);

	const hiddenAbove = startVisible > 0;
	const hiddenBelow = endVisible < hunk.lines.length;

	const rows: VNode[] = [];

	if (hiddenAbove) {
		rows.push(expandArrow(key, "above", dispatch));
	}

	// Find comments for this file
	const fileComments = model.comments.filter((c) => c.file === file.path);
	const draft = model.commentDraft;
	const draftEndLine = draft ? Math.max(draft.startLine, draft.endLine) : -1;
	let commentBoxInserted = false;

	for (let i = startVisible; i < endVisible; i++) {
		const line = hunk.lines[i]!;
		const hl = highlightedLines[lineOffset + i] ?? "";
		rows.push(lineView(line, hl, file, fileIdx, model, dispatch));

		// Render saved comments after the matching line
		const lineNum = line.newNum ?? line.oldNum;
		if (lineNum != null) {
			for (const comment of fileComments) {
				if (comment.endLine === lineNum) {
					rows.push(savedCommentView(comment, dispatch));
				}
			}

			// Insert comment draft box after the last selected line
			if (!commentBoxInserted && draft && draft.file === file.path && lineNum === draftEndLine) {
				const box = commentBoxView(model, dispatch);
				if (box) {
					rows.push(box);
					commentBoxInserted = true;
				}
			}
		}
	}

	if (hiddenBelow) {
		rows.push(expandArrow(key, "below", dispatch));
	}

	return rows;
};

// --- File View ---

const fileHeaderView = (file: FileDiff, fileIdx: number): VNode => {
	const stats = fileChangeStats(file);
	const pathParts: VNode[] = [];

	if (file.oldPath && file.oldPath !== file.path) {
		pathParts.push(h("span.file-path-old", file.oldPath));
		pathParts.push(h("span.file-rename-arrow", " \u2192 "));
	}
	pathParts.push(h("span.file-path", file.path));

	const statsNodes: VNode[] = [];
	if (stats.added > 0) statsNodes.push(h("span.file-stats-add", `+${stats.added}`));
	if (stats.added > 0 && stats.deleted > 0) statsNodes.push(h("span", " "));
	if (stats.deleted > 0) statsNodes.push(h("span.file-stats-del", `-${stats.deleted}`));

	return h("div.file-header", {
		attrs: { "data-file-idx": String(fileIdx) },
	}, [
		h("div", pathParts),
		h("span.file-change-stats", statsNodes),
	]);
};

const fileView = (
	file: FileDiff,
	fileIdx: number,
	model: Model,
	dispatch: (msg: Msg) => void,
): VNode => {
	const children: VNode[] = [fileHeaderView(file, fileIdx)];

	if (file.binary) {
		children.push(h("div.binary-notice", "Binary file not shown."));
		return h("div.file-section", { key: `${model.activeView}:${file.path}` }, children);
	}

	// Highlight all lines in the file at once (keyed by view to avoid stale cache across commits)
	const highlightedLines = highlightFile(file, model.activeView);

	const tableRows: VNode[] = [];
	let lineOffset = 0;

	for (let hunkIdx = 0; hunkIdx < file.hunks.length; hunkIdx++) {
		// Hunk separator between hunks
		if (hunkIdx > 0) {
			tableRows.push(
				h("tr.hunk-separator", { key: `sep-${fileIdx}-${hunkIdx}` }, [h("td", { attrs: { colspan: 2 } })]),
			);
		}

		const hunk = file.hunks[hunkIdx]!;
		const rows = hunkView(hunk, highlightedLines, lineOffset, file, fileIdx, hunkIdx, model, dispatch);
		tableRows.push(...rows);
		lineOffset += hunk.lines.length;
	}

	children.push(h("table.diff-table", [
		h("colgroup", [
			h("col", { style: { width: "55px" } }),
			h("col"),
		]),
		h("tbody", tableRows),
	]));

	if (file.truncated) {
		children.push(h("div.truncated-notice", "File truncated for display."));
	}

	return h("div.file-section", { key: `${model.activeView}:${file.path}` }, children);
};

// --- Diff Area ---

export const diffAreaView = (model: Model, dispatch: (msg: Msg) => void): VNode => {
	const data = model.data!;
	const diffData = data.diffs[model.activeView];
	const files = diffData?.files ?? [];

	if (files.length === 0) {
		return h("div.diff-area", [
			h("div.empty-state", "No files to display."),
		]);
	}

	return h("div.diff-area", files.map((file, idx) => fileView(file, idx, model, dispatch)));
};
