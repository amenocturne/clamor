// === Git & Diff Types ===

export type DiffLineType = "context" | "add" | "delete";

export type DiffLine = {
	readonly type: DiffLineType;
	readonly oldNum: number | null;
	readonly newNum: number | null;
	readonly content: string;
};

export type Hunk = {
	readonly oldStart: number;
	readonly newStart: number;
	readonly lines: readonly DiffLine[];
};

export type FileDiff = {
	readonly path: string;
	readonly oldPath?: string; // present for renames
	readonly language: string;
	readonly binary: boolean;
	readonly truncated: boolean;
	readonly hunks: readonly Hunk[];
};

export type DiffData = {
	readonly files: readonly FileDiff[];
};

export type Commit = {
	readonly hash: string;
	readonly message: string;
	readonly date: string;
};

// === API Types ===

export type ApiData = {
	readonly commits: readonly Commit[];
	readonly diffs: Readonly<Record<string, DiffData>>; // "combined" | commit hash
	readonly message: string | null;
	readonly repo: string;
	readonly project: string | null;
};

// === Review Types ===

export type CommentSeverity = "fix" | "suggestion" | "question";

export type ReviewVerdict = "approved" | "changes-requested";

export type ReviewComment = {
	readonly file: string;
	readonly startLine: number;
	readonly endLine: number;
	readonly type: CommentSeverity;
	readonly text: string;
	readonly code: string;
};

export type ReviewSubmission = {
	readonly verdict: ReviewVerdict;
	readonly summary: string;
	readonly comments: readonly ReviewComment[];
};

// === Frontend State Types ===

export type CommentDraft = {
	readonly file: string;
	readonly startLine: number;
	readonly endLine: number;
};

export type ContextExpansion = {
	readonly above: number;
	readonly below: number;
};

export type StoredComment = ReviewComment & {
	readonly id: string;
};

export type DragSelection = {
	readonly file: string;
	readonly startLine: number;
	readonly endLine: number;
};

export type Model = {
	readonly data: ApiData | null;
	readonly activeView: string; // "combined" | commit hash
	readonly contextExpansion: Readonly<Record<string, ContextExpansion>>; // key: `${fileIdx}-${hunkIdx}`
	readonly comments: readonly StoredComment[];
	readonly summary: string;
	readonly sidebarOpen: boolean;
	readonly commentDraft: CommentDraft | null;
	readonly dragSelection: DragSelection | null;
	readonly submitted: boolean;
	readonly error: string | null;
};

// === Frontend Message Types ===

export type Msg =
	| { readonly type: "dataLoaded"; readonly data: ApiData }
	| { readonly type: "dataError"; readonly error: string }
	| { readonly type: "setActiveView"; readonly view: string }
	| { readonly type: "expandContext"; readonly key: string; readonly direction: "above" | "below" }
	| { readonly type: "startDrag"; readonly file: string; readonly startLine: number }
	| { readonly type: "updateDrag"; readonly endLine: number }
	| { readonly type: "endDrag" }
	| { readonly type: "startComment"; readonly draft: CommentDraft }
	| { readonly type: "cancelComment" }
	| {
			readonly type: "saveComment";
			readonly severity: CommentSeverity;
			readonly text: string;
			readonly code: string;
	  }
	| { readonly type: "editComment"; readonly id: string }
	| { readonly type: "deleteComment"; readonly id: string }
	| { readonly type: "setSummary"; readonly summary: string }
	| { readonly type: "toggleSidebar" }
	| { readonly type: "submit"; readonly verdict: ReviewVerdict }
	| { readonly type: "submitted" };
