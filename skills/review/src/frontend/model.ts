import type { Model } from "../types.ts";

export const initialModel: Model = {
	data: null,
	activeView: "combined",
	contextExpansion: {},
	comments: [],
	summary: "",
	sidebarOpen: true,
	commentDraft: null,
	submitted: false,
	error: null,
};
