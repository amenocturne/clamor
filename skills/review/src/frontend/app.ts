import {
	attributesModule,
	classModule,
	eventListenersModule,
	init,
	propsModule,
	styleModule,
} from "snabbdom";
import type { VNode } from "snabbdom";
import type { CommentSnapshot, Model, Msg, ReviewSubmission } from "../types.ts";
import { initialModel } from "./model.ts";
import { update } from "./update.ts";
import { getDraftText, resetDraftKey } from "./view/comment.ts";
import { rootView } from "./view/root.ts";

const patch = init([classModule, propsModule, styleModule, eventListenersModule, attributesModule]);

let model: Model = initialModel;
let vnode: VNode | Element = document.getElementById("app")!;

// --- Undo/Redo for comment operations ---

const MAX_UNDO = 50;
const undoStack: CommentSnapshot[] = [];
let redoStack: CommentSnapshot[] = [];

const UNDOABLE_MSGS = new Set(["saveComment", "deleteComment", "editComment", "cancelComment"]);

const captureSnapshot = (): CommentSnapshot => ({
	comments: model.comments,
	commentDraft: model.commentDraft ? { ...model.commentDraft, initialText: getDraftText() } : null,
});

const restoreSnapshot = (snapshot: CommentSnapshot): void => {
	model = {
		...model,
		comments: snapshot.comments,
		commentDraft: snapshot.commentDraft,
	};
	resetDraftKey();
};

const performUndo = (): void => {
	if (undoStack.length === 0) return;
	redoStack.push(captureSnapshot());
	restoreSnapshot(undoStack.pop()!);
	render();
};

const performRedo = (): void => {
	if (redoStack.length === 0) return;
	undoStack.push(captureSnapshot());
	restoreSnapshot(redoStack.pop()!);
	render();
};

const dispatch = (msg: Msg): void => {
	if (UNDOABLE_MSGS.has(msg.type)) {
		undoStack.push(captureSnapshot());
		if (undoStack.length > MAX_UNDO) undoStack.shift();
		redoStack = [];
	}

	const prev = model;
	model = update(model, msg);

	if (msg.type === "fetchPastReview") {
		fetch(`/api/reviews/${encodeURIComponent(msg.filename)}`)
			.then((r) => r.json())
			.then((data: { content: string }) =>
				dispatch({ type: "viewPastReview", content: data.content }),
			);
	}

	if (msg.type === "deletePastReview") {
		fetch(`/api/reviews/${encodeURIComponent(msg.filename)}`, { method: "DELETE" }).then(() =>
			dispatch({ type: "reviewDeleted", filename: msg.filename }),
		);
	}

	if (msg.type === "submit" && !prev.submitted) {
		const submission: ReviewSubmission = {
			verdict: msg.verdict,
			summary: model.summary,
			comments: [...model.comments],
		};
		fetch("/api/submit", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(submission),
		}).then(() => window.close());
	}

	render();
};

const render = (): void => {
	const newVnode = rootView(model, dispatch);
	vnode = patch(vnode, newVnode);
};

// --- Keyboard Navigation Helpers ---

const scrollToNextFile = (direction: 1 | -1): void => {
	const headers = Array.from(document.querySelectorAll(".file-header"));
	if (headers.length === 0) return;

	// Find the header closest to the top of the viewport
	let closestIdx = 0;
	let closestDist = Number.POSITIVE_INFINITY;
	for (let i = 0; i < headers.length; i++) {
		const rect = headers[i]!.getBoundingClientRect();
		const dist = Math.abs(rect.top);
		if (dist < closestDist) {
			closestDist = dist;
			closestIdx = i;
		}
	}

	// If current header is near the top (within 5px), move to next/prev;
	// otherwise, direction=1 goes to current, direction=-1 goes to prev
	const currentRect = headers[closestIdx]!.getBoundingClientRect();
	let targetIdx: number;
	if (Math.abs(currentRect.top) < 5) {
		targetIdx = closestIdx + direction;
	} else {
		targetIdx = direction === 1 ? closestIdx : closestIdx - 1;
		// If we're scrolled past the closest header, go forward
		if (currentRect.top < 0 && direction === 1) {
			targetIdx = closestIdx + 1;
		}
	}

	targetIdx = Math.max(0, Math.min(headers.length - 1, targetIdx));
	const target = headers[targetIdx]!;
	target.scrollIntoView({ behavior: "smooth", block: "start" });

	// Remove existing highlights, add to target
	for (const el of headers) el.classList.remove("highlighted");
	target.classList.add("highlighted");
	setTimeout(() => target.classList.remove("highlighted"), 1200);
};

const navigateCommit = (direction: 1 | -1): void => {
	if (!model.data) return;
	const commits = model.data.commits;

	// Build ordered list: "combined" then each commit hash
	const views = ["combined", ...commits.map((c) => c.hash)];
	const currentIdx = views.indexOf(model.activeView);
	if (currentIdx === -1) return;

	const nextIdx = currentIdx + direction;
	if (nextIdx < 0 || nextIdx >= views.length) return;

	dispatch({ type: "setActiveView", view: views[nextIdx]! });
};

// --- Global Keyboard Shortcuts ---

document.addEventListener("keydown", (e) => {
	// Cmd+O / Ctrl+O: Open file search (always available)
	if (e.key === "o" && (e.metaKey || e.ctrlKey)) {
		e.preventDefault();
		if (model.fileSearchOpen) {
			dispatch({ type: "closeFileSearch" });
		} else {
			dispatch({ type: "openFileSearch" });
		}
		return;
	}

	// When file search is open, let its own input handle keys
	if (model.fileSearchOpen) {
		if (e.key === "Escape") {
			e.preventDefault();
			dispatch({ type: "closeFileSearch" });
		}
		return;
	}

	const target = e.target as HTMLElement;
	const isInput = target.tagName === "TEXTAREA" || target.tagName === "INPUT";

	// Escape: Close comment box
	if (e.key === "Escape" && model.commentDraft) {
		e.preventDefault();
		dispatch({ type: "cancelComment" });
		return;
	}

	// Shortcuts below only fire when not focused in a text input
	if (isInput) return;

	// Cmd+Z / Ctrl+Z: Undo comment action
	if (e.key === "z" && (e.metaKey || e.ctrlKey) && !e.shiftKey) {
		e.preventDefault();
		performUndo();
		return;
	}

	// Cmd+Shift+Z / Ctrl+Shift+Z: Redo comment action
	if (e.key === "z" && (e.metaKey || e.ctrlKey) && e.shiftKey) {
		e.preventDefault();
		performRedo();
		return;
	}

	// j/k: Next/previous file
	if (e.key === "j") {
		scrollToNextFile(1);
	}
	if (e.key === "k") {
		scrollToNextFile(-1);
	}

	// [/]: Previous/next commit
	if (e.key === "[") {
		navigateCommit(-1);
	}
	if (e.key === "]") {
		navigateCommit(1);
	}
});

export const startApp = (fetchData: () => Promise<void>): void => {
	render();
	fetchData();
};

export { dispatch, render };
