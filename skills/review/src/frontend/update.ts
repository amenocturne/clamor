import type { Model, Msg, StoredComment, ContextExpansion } from "../types.ts";

let commentIdCounter = 0;

export const update = (model: Model, msg: Msg): Model => {
	switch (msg.type) {
		case "dataLoaded":
			return { ...model, data: msg.data, error: null };
		case "dataError":
			return { ...model, error: msg.error };
		case "setActiveView":
			return { ...model, activeView: msg.view };
		case "expandContext": {
			const current: ContextExpansion = model.contextExpansion[msg.key] ?? { above: 3, below: 3 };
			const updated: ContextExpansion =
				msg.direction === "above"
					? { ...current, above: current.above + 20 }
					: { ...current, below: current.below + 20 };
			return { ...model, contextExpansion: { ...model.contextExpansion, [msg.key]: updated } };
		}
		case "startComment":
			return { ...model, commentDraft: msg.draft };
		case "cancelComment":
			return { ...model, commentDraft: null };
		case "saveComment": {
			if (!model.commentDraft) return model;
			const id = `comment-${++commentIdCounter}`;
			const newComment: StoredComment = {
				id,
				file: model.commentDraft.file,
				startLine: model.commentDraft.startLine,
				endLine: model.commentDraft.endLine,
				type: msg.severity,
				text: msg.text,
				code: msg.code,
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
				commentDraft: { file: comment.file, startLine: comment.startLine, endLine: comment.endLine },
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
	}
};
