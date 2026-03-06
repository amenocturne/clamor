import { h } from "snabbdom";
import type { VNode } from "snabbdom";
import type { Model, Msg, StoredComment, CommentSeverity } from "../../types.ts";

// --- Ephemeral UI state for the comment draft box ---

let activeSeverity: CommentSeverity = "suggestion";
let draftText = "";

// Reset ephemeral state when a new draft opens
let lastDraftKey: string | null = null;

// Track which element had focus before the comment box opened, for focus restoration
let previousFocusElement: HTMLElement | null = null;

const captureFocus = (): void => {
	const active = document.activeElement as HTMLElement | null;
	if (active && active !== document.body) {
		previousFocusElement = active;
	}
};

const restoreFocus = (): void => {
	if (previousFocusElement) {
		previousFocusElement.focus();
		previousFocusElement = null;
	}
};

const draftKey = (model: Model): string | null => {
	if (!model.commentDraft) return null;
	return `${model.commentDraft.file}:${model.commentDraft.startLine}-${model.commentDraft.endLine}`;
};

const extractCode = (model: Model): string => {
	if (!model.commentDraft || !model.data) return "";
	const diffData = model.data.diffs[model.activeView] ?? model.data.diffs["combined"];
	if (!diffData) return "";
	const file = diffData.files.find((f) => f.path === model.commentDraft!.file);
	if (!file) return "";
	const { startLine, endLine } = model.commentDraft;
	const codeLines: string[] = [];
	for (const hunk of file.hunks) {
		for (const line of hunk.lines) {
			if (line.newNum != null && line.newNum >= startLine && line.newNum <= endLine) {
				codeLines.push(line.content);
			}
		}
	}
	return codeLines.join("\n");
};

// --- Focus trap for the comment box ---

const handleCommentBoxKeydown = (e: KeyboardEvent): void => {
	if (e.key !== "Tab") return;

	const container = (e.currentTarget as HTMLElement);
	const focusable = Array.from(
		container.querySelectorAll<HTMLElement>("button, textarea"),
	);
	if (focusable.length === 0) return;

	const first = focusable[0]!;
	const last = focusable[focusable.length - 1]!;

	if (e.shiftKey) {
		if (document.activeElement === first) {
			e.preventDefault();
			last.focus();
		}
	} else {
		if (document.activeElement === last) {
			e.preventDefault();
			first.focus();
		}
	}
};

// --- Severity Pill ---

const severityPill = (severity: CommentSeverity): VNode =>
	h("button.severity-pill", {
		class: { active: activeSeverity === severity, [severity]: true },
		attrs: { "aria-label": `Set severity to ${severity}`, "aria-pressed": String(activeSeverity === severity) },
		on: {
			click: (e: Event) => {
				e.preventDefault();
				activeSeverity = severity;
				const bar = (e.target as HTMLElement).parentElement;
				if (bar) {
					for (const child of Array.from(bar.children)) {
						child.classList.remove("active");
						child.setAttribute("aria-pressed", "false");
					}
					(e.target as HTMLElement).classList.add("active");
					(e.target as HTMLElement).setAttribute("aria-pressed", "true");
				}
			},
		},
	}, severity);

// --- Comment Draft Box ---

export const commentBoxView = (model: Model, dispatch: (msg: Msg) => void): VNode | null => {
	if (!model.commentDraft) return null;

	const key = draftKey(model);
	if (key !== lastDraftKey) {
		// New draft opened — reset ephemeral state and capture focus for restoration
		captureFocus();
		activeSeverity = "suggestion";
		draftText = "";
		lastDraftKey = key;
	}

	return h("tr.comment-box-row", { key: `draft-${model.commentDraft.file}:${model.commentDraft.startLine}` }, [
		h("td", { attrs: { colspan: 2 } }, [
			h("div.comment-box", {
				attrs: { role: "dialog", "aria-label": "Add comment" },
				on: { keydown: handleCommentBoxKeydown },
			}, [
				h("div.comment-severity-bar", { attrs: { role: "group", "aria-label": "Comment severity" } }, [
					severityPill("fix"),
					severityPill("suggestion"),
					severityPill("question"),
				]),
				h("textarea.comment-textarea", {
					props: { value: draftText, placeholder: "Add your comment..." },
					attrs: { "aria-label": "Comment text" },
					hook: {
						insert: (vnode) => {
							const el = vnode.elm as HTMLTextAreaElement;
							el.focus();
						},
					},
					on: {
						input: (e: Event) => {
							draftText = (e.target as HTMLTextAreaElement).value;
						},
						keydown: (e: KeyboardEvent) => {
							if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
								e.preventDefault();
								const code = extractCode(model);
								dispatch({ type: "saveComment", severity: activeSeverity, text: draftText, code });
								draftText = "";
								lastDraftKey = null;
								restoreFocus();
							}
							if (e.key === "Escape") {
								e.preventDefault();
								dispatch({ type: "cancelComment" });
								draftText = "";
								lastDraftKey = null;
								restoreFocus();
							}
						},
					},
				}),
				h("div.comment-actions", [
					h("button.btn.btn-ghost", {
						attrs: { "aria-label": "Cancel comment" },
						on: {
							click: () => {
								dispatch({ type: "cancelComment" });
								draftText = "";
								lastDraftKey = null;
								restoreFocus();
							},
						},
					}, "Cancel"),
					h("button.btn.btn-primary", {
						attrs: { "aria-label": "Save comment" },
						on: {
							click: () => {
								const code = extractCode(model);
								dispatch({ type: "saveComment", severity: activeSeverity, text: draftText, code });
								draftText = "";
								lastDraftKey = null;
								restoreFocus();
							},
						},
					}, "Save"),
				]),
			]),
		]),
	]);
};

// --- Saved Comment Banner ---

export const savedCommentView = (comment: StoredComment, dispatch: (msg: Msg) => void): VNode =>
	h("tr.comment-box-row", {
		key: `comment-${comment.id}`,
		attrs: { "data-comment-id": comment.id },
	}, [
		h("td", { attrs: { colspan: 2 } }, [
			h(`div.saved-comment.${comment.type}`, {
				on: { click: () => dispatch({ type: "editComment", id: comment.id }) },
			}, [
				h("div.saved-comment-header", [
					h(`span.saved-comment-severity.${comment.type}`, comment.type.toUpperCase()),
					h("span.saved-comment-location", `${comment.file}:${comment.startLine}`),
				]),
				h("div", comment.text),
			]),
		]),
	]);
