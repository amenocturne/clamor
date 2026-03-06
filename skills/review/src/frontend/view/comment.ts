import { h } from "snabbdom";
import type { VNode } from "snabbdom";
import type { Model, Msg, StoredComment, CommentSeverity } from "../../types.ts";

// --- Ephemeral UI state for the comment draft box ---

let activeSeverity: CommentSeverity = "suggestion";
let draftText = "";

// Reset ephemeral state when a new draft opens
let lastDraftKey: string | null = null;

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

// --- Severity Pill ---

const severityPill = (severity: CommentSeverity): VNode =>
	h("button.severity-pill", {
		class: { active: activeSeverity === severity, [severity]: true },
		on: {
			click: (e: Event) => {
				e.preventDefault();
				activeSeverity = severity;
				// Force re-render by triggering a no-op DOM update isn't needed;
				// Snabbdom will pick up class changes on next patch via the closure.
				// We need to trigger a re-render somehow. The simplest way: update the
				// textarea's internal state. But since severity is ephemeral, we just
				// update the module var and let the next render pick it up.
				// Actually, clicking the pill won't trigger a dispatch, so no re-render.
				// We need to manually update the DOM classes.
				const bar = (e.target as HTMLElement).parentElement;
				if (bar) {
					for (const child of Array.from(bar.children)) {
						child.classList.remove("active");
					}
					(e.target as HTMLElement).classList.add("active");
				}
			},
		},
	}, severity);

// --- Comment Draft Box ---

export const commentBoxView = (model: Model, dispatch: (msg: Msg) => void): VNode | null => {
	if (!model.commentDraft) return null;

	const key = draftKey(model);
	if (key !== lastDraftKey) {
		// New draft opened — reset ephemeral state
		activeSeverity = "suggestion";
		draftText = "";
		lastDraftKey = key;
	}

	return h("tr.comment-box-row", [
		h("td", { attrs: { colspan: 3 } }, [
			h("div.comment-box", [
				h("div.comment-severity-bar", [
					severityPill("fix"),
					severityPill("suggestion"),
					severityPill("question"),
				]),
				h("textarea.comment-textarea", {
					props: { value: draftText, placeholder: "Add your comment..." },
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
							}
							if (e.key === "Escape") {
								e.preventDefault();
								dispatch({ type: "cancelComment" });
								draftText = "";
								lastDraftKey = null;
							}
						},
					},
				}),
				h("div.comment-actions", [
					h("button.btn.btn-ghost", {
						on: {
							click: () => {
								dispatch({ type: "cancelComment" });
								draftText = "";
								lastDraftKey = null;
							},
						},
					}, "Cancel"),
					h("button.btn.btn-primary", {
						on: {
							click: () => {
								const code = extractCode(model);
								dispatch({ type: "saveComment", severity: activeSeverity, text: draftText, code });
								draftText = "";
								lastDraftKey = null;
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
		attrs: { "data-comment-id": comment.id },
	}, [
		h("td", { attrs: { colspan: 3 } }, [
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
