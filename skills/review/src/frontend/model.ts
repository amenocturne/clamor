import type { Model } from "../types.ts";

const loadSidebarWidth = (): number => {
	try {
		const saved = localStorage.getItem("reviewSidebarWidth");
		if (saved) {
			const w = Number(saved);
			if (w >= 180 && w <= 600) return w;
		}
	} catch {}
	return 240;
};

export const initialModel: Model = {
	data: null,
	activeView: "combined",
	contextExpansion: {},
	comments: [],
	summary: "",
	sidebarOpen: true,
	commentDraft: null,
	dragSelection: null,
	submitted: false,
	error: null,
	pastReviews: [],
	viewingPastReview: null,
	fileSearchOpen: false,
	fileSearchQuery: "",
	fileSearchSelectedIdx: 0,
	collapsedDirs: new Set(),
	sidebarWidth: loadSidebarWidth(),
};
