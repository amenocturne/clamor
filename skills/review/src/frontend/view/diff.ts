import { h } from "snabbdom";
import type { VNode } from "snabbdom";
import hljs from "highlight.js";
import type { Model, Msg, FileDiff, Hunk, DiffLine, ContextExpansion, StoredComment } from "../../types.ts";
import { savedCommentView } from "./comment.ts";

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

const highlightFile = (file: FileDiff): readonly string[] => {
	const allContent = file.hunks.flatMap((hunk) => hunk.lines.map((l) => l.content));
	const joined = allContent.join("\n");

	let highlighted: string;
	try {
		const result = hljs.highlight(joined, { language: file.language });
		highlighted = result.value;
	} catch {
		highlighted = joined.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
	}

	return highlighted.split("\n");
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
	dispatch: (msg: Msg) => void,
): VNode => {
	const lineClass =
		line.type === "add" ? "line-add" : line.type === "delete" ? "line-del" : "line-context";

	return h(`tr.${lineClass}`, [
		h("td.gutter", line.oldNum != null ? String(line.oldNum) : ""),
		h("td.gutter.gutter-new", {
			on: {
				mousedown: () => {
					const lineNum = line.newNum ?? line.oldNum;
					if (lineNum != null) {
						dispatch({
							type: "startComment",
							draft: { file: file.path, startLine: lineNum, endLine: lineNum },
						});
					}
				},
			},
		}, line.newNum != null ? String(line.newNum) : ""),
		lineContentCell(highlighted),
	]);
};

// --- Expand Arrows ---

const expandArrow = (key: string, direction: "above" | "below", dispatch: (msg: Msg) => void): VNode =>
	h("tr.expand-row", {
		on: { click: () => dispatch({ type: "expandContext", key, direction }) },
	}, [
		h("td", { attrs: { colspan: 3 } }, direction === "above" ? "▲ Show more" : "▼ Show more"),
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

	for (let i = startVisible; i < endVisible; i++) {
		const line = hunk.lines[i]!;
		const hl = highlightedLines[lineOffset + i] ?? "";
		rows.push(lineView(line, hl, file, fileIdx, dispatch));

		// Render saved comments after the matching line
		const lineNum = line.newNum ?? line.oldNum;
		if (lineNum != null) {
			for (const comment of fileComments) {
				if (comment.endLine === lineNum) {
					rows.push(savedCommentView(comment, dispatch));
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
		pathParts.push(h("span.file-rename-arrow", " → "));
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
		return h("div.file-section", { key: `file-${fileIdx}` }, children);
	}

	// Highlight all lines in the file at once
	const highlightedLines = highlightFile(file);

	const tableRows: VNode[] = [];
	let lineOffset = 0;

	for (let hunkIdx = 0; hunkIdx < file.hunks.length; hunkIdx++) {
		// Hunk separator between hunks
		if (hunkIdx > 0) {
			tableRows.push(
				h("tr.hunk-separator", [h("td", { attrs: { colspan: 3 } })]),
			);
		}

		const hunk = file.hunks[hunkIdx]!;
		const rows = hunkView(hunk, highlightedLines, lineOffset, file, fileIdx, hunkIdx, model, dispatch);
		tableRows.push(...rows);
		lineOffset += hunk.lines.length;
	}

	children.push(h("table.diff-table", [h("tbody", tableRows)]));

	if (file.truncated) {
		children.push(h("div.truncated-notice", "File truncated for display."));
	}

	return h("div.file-section", { key: `file-${fileIdx}` }, children);
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
