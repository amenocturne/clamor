import type { ContextExpansion, Model, Msg, StoredComment } from "../types.ts";

let commentIdCounter = 0;

export const update = (model: Model, msg: Msg): Model => {
	switch (msg.type) {
		case "dataLoaded":
			return { ...model, data: msg.data, error: null };
		case "dataError":
			return { ...model, error: msg.error };
		case "setActiveView":
			return { ...model, activeView: msg.view, contextExpansion: {} };
		case "expandContext": {
			const isGap = msg.key.includes("-gap-");
			const current: ContextExpansion =
				model.contextExpansion[msg.key] ??
				(isGap ? { above: 0, below: 0 } : { above: 3, below: 3 });
			const updated: ContextExpansion =
				msg.direction === "above"
					? { ...current, above: current.above + 20 }
					: { ...current, below: current.below + 20 };
			return { ...model, contextExpansion: { ...model.contextExpansion, [msg.key]: updated } };
		}
		case "startDrag":
			return {
				...model,
				dragSelection: { file: msg.file, startLine: msg.startLine, endLine: msg.startLine },
				commentDraft: null,
			};
		case "updateDrag": {
			if (!model.dragSelection) return model;
			return { ...model, dragSelection: { ...model.dragSelection, endLine: msg.endLine } };
		}
		case "endDrag": {
			if (!model.dragSelection) return model;
			const lo = Math.min(model.dragSelection.startLine, model.dragSelection.endLine);
			const hi = Math.max(model.dragSelection.startLine, model.dragSelection.endLine);
			return {
				...model,
				dragSelection: null,
				commentDraft: {
					file: model.dragSelection.file,
					startLine: lo,
					endLine: hi,
					...(model.dragSelection.selectedText
						? { selectedText: model.dragSelection.selectedText }
						: {}),
				},
			};
		}
		case "startComment":
			return { ...model, commentDraft: msg.draft, dragSelection: null };
		case "cancelComment":
			return { ...model, commentDraft: null };
		case "textSelected": {
			return {
				...model,
				commentDraft: {
					file: msg.file,
					startLine: msg.startLine,
					endLine: msg.endLine,
					selectedText: msg.selectedText,
				},
				dragSelection: null,
			};
		}
		case "saveComment": {
			if (!model.commentDraft) return model;
			const id = `comment-${++commentIdCounter}`;
			const newComment: StoredComment = {
				id,
				file: model.commentDraft.file,
				startLine: model.commentDraft.startLine,
				endLine: model.commentDraft.endLine,
				text: msg.text,
				code: msg.code,
				...(model.commentDraft.selectedText
					? { selectedText: model.commentDraft.selectedText }
					: {}),
			};
			return {
				...model,
				comments: [...model.comments, newComment],
				commentDraft: null,
			};
		}
		case "editComment": {
			const comment = model.comments.find((c) => c.id === msg.id);
			if (!comment) return model;
			return {
				...model,
				commentDraft: {
					file: comment.file,
					startLine: comment.startLine,
					endLine: comment.endLine,
					initialText: comment.text,
					...(comment.selectedText ? { selectedText: comment.selectedText } : {}),
				},
				comments: model.comments.filter((c) => c.id !== msg.id),
			};
		}
		case "deleteComment":
			return { ...model, comments: model.comments.filter((c) => c.id !== msg.id) };
		case "setSummary":
			return { ...model, summary: msg.summary };
		case "toggleSidebar":
			return { ...model, sidebarOpen: !model.sidebarOpen };
		case "submit":
			return { ...model, submitted: true };
		case "submitted":
			return { ...model, submitted: true };
		case "pastReviewsLoaded":
			return { ...model, pastReviews: msg.reviews };
		case "fetchPastReview":
			return model;
		case "deletePastReview":
			return model;
		case "viewPastReview":
			return { ...model, viewingPastReview: msg.content };
		case "closePastReview":
			return { ...model, viewingPastReview: null };
		case "reviewDeleted":
			return {
				...model,
				pastReviews: model.pastReviews.filter((r) => r.filename !== msg.filename),
			};
		case "openFileSearch":
			return { ...model, fileSearchOpen: true, fileSearchQuery: "", fileSearchSelectedIdx: 0 };
		case "closeFileSearch":
			return { ...model, fileSearchOpen: false, fileSearchQuery: "", fileSearchSelectedIdx: 0 };
		case "setFileSearchQuery":
			return { ...model, fileSearchQuery: msg.query, fileSearchSelectedIdx: 0 };
		case "fileSearchNavigate": {
			const diffData = model.data?.diffs[model.activeView];
			const files = diffData?.files ?? [];
			const query = model.fileSearchQuery.toLowerCase();
			const matchCount = query
				? files.filter((f) => f.path.toLowerCase().includes(query)).length
				: files.length;
			if (matchCount === 0) return model;
			const next = model.fileSearchSelectedIdx + msg.direction;
			return {
				...model,
				fileSearchSelectedIdx: Math.max(0, Math.min(matchCount - 1, next)),
			};
		}
		case "toggleDir": {
			const dirs = new Set(model.collapsedDirs);
			if (dirs.has(msg.path)) {
				dirs.delete(msg.path);
			} else {
				dirs.add(msg.path);
			}
			return { ...model, collapsedDirs: dirs };
		}
	}
};
