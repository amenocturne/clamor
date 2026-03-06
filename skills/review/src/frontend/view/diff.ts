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

// Compute visible segments for a hunk — folds long context gaps between change clusters
type Segment = { readonly start: number; readonly end: number };

const DEFAULT_CONTEXT = 3;
const GAP_THRESHOLD = 2 * DEFAULT_CONTEXT + 1;

const computeVisibleSegments = (
	lines: readonly DiffLine[],
	hunkKey: string,
	expansions: Readonly<Record<string, ContextExpansion>>,
): readonly Segment[] => {
	const changes: number[] = [];
	for (let i = 0; i < lines.length; i++) {
		if (lines[i]!.type !== "context") changes.push(i);
	}

	if (changes.length === 0) {
		return [{ start: 0, end: lines.length }];
	}

	// Group changes into clusters (merge if gap between them is small)
	const clusters: { first: number; last: number }[] = [];
	let cFirst = changes[0]!;
	let cLast = changes[0]!;

	for (let i = 1; i < changes.length; i++) {
		if (changes[i]! - cLast > GAP_THRESHOLD) {
			clusters.push({ first: cFirst, last: cLast });
			cFirst = changes[i]!;
		}
		cLast = changes[i]!;
	}
	clusters.push({ first: cFirst, last: cLast });

	const outer = expansions[hunkKey] ?? { above: DEFAULT_CONTEXT, below: DEFAULT_CONTEXT };

	return clusters.map((cluster, i) => {
		const start = i === 0
			? Math.max(0, cluster.first - outer.above)
			: Math.max(0, cluster.first - DEFAULT_CONTEXT - (expansions[`${hunkKey}-gap-${i - 1}`]?.above ?? 0));

		const end = i === clusters.length - 1
			? Math.min(lines.length, cluster.last + 1 + outer.below)
			: Math.min(lines.length, cluster.last + 1 + DEFAULT_CONTEXT + (expansions[`${hunkKey}-gap-${i}`]?.above ?? 0));

		return { start, end };
	});
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

const foldArrow = (key: string, hiddenCount: number, dispatch: (msg: Msg) => void): VNode =>
	h("tr.fold-row", {
		key: `fold-${key}`,
		attrs: {
			role: "button",
			tabindex: "0",
			"aria-label": `Show ${hiddenCount} hidden lines`,
		},
		on: {
			click: () => dispatch({ type: "expandContext", key, direction: "above" }),
			keydown: (e: KeyboardEvent) => {
				if (e.key === "Enter" || e.key === " ") {
					e.preventDefault();
					dispatch({ type: "expandContext", key, direction: "above" });
				}
			},
		},
	}, [
		h("td", { attrs: { colspan: 2 } }, `\u22EF ${hiddenCount} lines \u22EF`),
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
	const hunkKey = `${fileIdx}-${hunkIdx}`;
	const segments = computeVisibleSegments(hunk.lines, hunkKey, model.contextExpansion);

	const rows: VNode[] = [];

	// Outer expand above
	if (segments[0]!.start > 0) {
		rows.push(expandArrow(hunkKey, "above", dispatch));
	}

	const fileComments = model.comments.filter((c) => c.file === file.path);
	const draft = model.commentDraft;
	const draftEndLine = draft ? Math.max(draft.startLine, draft.endLine) : -1;
	let commentBoxInserted = false;

	let prevEnd = segments[0]!.start;

	for (let segIdx = 0; segIdx < segments.length; segIdx++) {
		const seg = segments[segIdx]!;
		const actualStart = Math.max(seg.start, prevEnd);

		if (actualStart >= seg.end) continue;

		// Fold arrow between segments when there's a gap
		if (segIdx > 0 && actualStart > prevEnd) {
			const gapKey = `${hunkKey}-gap-${segIdx - 1}`;
			rows.push(foldArrow(gapKey, actualStart - prevEnd, dispatch));
		}

		for (let i = actualStart; i < seg.end; i++) {
			const line = hunk.lines[i]!;
			const hl = highlightedLines[lineOffset + i] ?? "";
			rows.push(lineView(line, hl, file, fileIdx, model, dispatch));

			const newNum = line.newNum;
			if (newNum != null) {
				for (const comment of fileComments) {
					if (comment.endLine === newNum) {
						rows.push(savedCommentView(comment, dispatch));
					}
				}

				if (!commentBoxInserted && draft && draft.file === file.path && newNum === draftEndLine) {
					const box = commentBoxView(model, dispatch);
					if (box) {
						rows.push(box);
						commentBoxInserted = true;
					}
				}
			}
		}

		prevEnd = Math.max(prevEnd, seg.end);
	}

	// Outer expand below
	if (prevEnd < hunk.lines.length) {
		rows.push(expandArrow(hunkKey, "below", dispatch));
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
