import { h } from "snabbdom";
import type { VNode } from "snabbdom";
import type { Model, Msg, FileDiff, Hunk, DiffLine } from "../../types.ts";

const fileStats = (file: FileDiff): { added: number; deleted: number } => {
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

const scrollToFile = (fileIdx: number): void => {
	const el = document.querySelector(`[data-file-idx="${fileIdx}"]`);
	if (!el) return;
	el.scrollIntoView({ behavior: "smooth", block: "start" });
	el.classList.add("highlighted");
	setTimeout(() => el.classList.remove("highlighted"), 1200);
};

const commitsSection = (model: Model, dispatch: (msg: Msg) => void): VNode => {
	const data = model.data!;
	const items: VNode[] = [
		h("div.commit-item", {
			class: { active: model.activeView === "combined" },
			on: { click: () => dispatch({ type: "setActiveView", view: "combined" }) },
		}, [
			h("span.commit-radio"),
			h("span.commit-msg", "All changes"),
		]),
	];

	for (const commit of data.commits) {
		items.push(
			h("div.commit-item", {
				class: { active: model.activeView === commit.hash },
				on: { click: () => dispatch({ type: "setActiveView", view: commit.hash }) },
			}, [
				h("span.commit-radio"),
				h("span.commit-hash", commit.hash.slice(0, 7)),
				h("span.commit-msg", commit.message),
			]),
		);
	}

	return h("div.sidebar-section", [
		h("div.sidebar-label", "Commits"),
		...items,
	]);
};

const filesSection = (model: Model): VNode => {
	const data = model.data!;
	const diffData = data.diffs[model.activeView];
	const files = diffData?.files ?? [];

	return h("div.sidebar-section", [
		h("div.sidebar-label", "Files"),
		...files.map((file, idx) => {
			const stats = fileStats(file);
			return h("div.file-item", {
				on: { click: () => scrollToFile(idx) },
			}, [
				h("span", file.path.split("/").pop() ?? file.path),
				h("span.file-stats", [
					stats.added > 0 ? h("span.file-stats-add", `+${stats.added}`) : null,
					stats.added > 0 && stats.deleted > 0 ? " " : null,
					stats.deleted > 0 ? h("span.file-stats-del", `-${stats.deleted}`) : null,
				].filter(Boolean) as VNode[]),
			]);
		}),
	]);
};

const descriptionSection = (model: Model): VNode | null => {
	const message = model.data?.message;
	if (!message) return null;

	return h("div.sidebar-section", [
		h("div.sidebar-label", "Description"),
		h("div.description-text", message),
	]);
};

const summarySection = (model: Model, dispatch: (msg: Msg) => void): VNode =>
	h("div.sidebar-section", [
		h("div.sidebar-label", "Summary"),
		h("textarea.summary-textarea", {
			props: { value: model.summary, placeholder: "Add review summary..." },
			on: {
				input: (e: Event) => {
					const target = e.target as HTMLTextAreaElement;
					dispatch({ type: "setSummary", summary: target.value });
				},
			},
		}),
	]);

const commentsSection = (model: Model): VNode | null => {
	if (model.comments.length === 0) return null;

	const diffData = model.data?.diffs[model.activeView];
	const visibleFiles = new Set(diffData?.files.map((f) => f.path) ?? []);

	return h("div.sidebar-section", [
		h("div.sidebar-label", `Comments (${model.comments.length})`),
		...model.comments.map((comment) => {
			const isVisible = visibleFiles.has(comment.file);
			const location = comment.startLine === comment.endLine
				? `${comment.file.split("/").pop()}:${comment.startLine}`
				: `${comment.file.split("/").pop()}:${comment.startLine}-${comment.endLine}`;

			return h("div.comment-list-item", {
				class: { dimmed: !isVisible },
				on: {
					click: () => {
						const commentEl = document.querySelector(`[data-comment-id="${comment.id}"]`);
						if (commentEl) {
							commentEl.scrollIntoView({ behavior: "smooth", block: "center" });
						}
					},
				},
			}, [
				h(`span.severity-dot.${comment.type}`),
				h("span", location),
			]);
		}),
	]);
};

const pastReviewsSection = (model: Model, dispatch: (msg: Msg) => void): VNode | null => {
	if (model.pastReviews.length === 0) return null;

	return h("div.sidebar-section", [
		h("div.sidebar-label", "Past Reviews"),
		...model.pastReviews.map((review) => {
			const name = review.filename.replace(/\.md$/, "");
			return h("div.past-review-item", [
				h("span.past-review-name", {
					on: { click: () => dispatch({ type: "fetchPastReview", filename: review.filename }) },
				}, name),
				h("button.btn-delete-review", {
					attrs: { "aria-label": `Delete review ${name}` },
					on: {
						click: (e: Event) => {
							e.stopPropagation();
							if (confirm("Delete this review?")) {
								dispatch({ type: "deletePastReview", filename: review.filename });
							}
						},
					},
				}, "\u00D7"),
			]);
		}),
	]);
};

export const sidebarView = (model: Model, dispatch: (msg: Msg) => void): VNode => {
	const sections: (VNode | null)[] = [
		commitsSection(model, dispatch),
		filesSection(model),
		descriptionSection(model),
		summarySection(model, dispatch),
		commentsSection(model),
		pastReviewsSection(model, dispatch),
	];

	return h("div.sidebar", {
		class: { hidden: !model.sidebarOpen },
	}, sections.filter(Boolean) as VNode[]);
};
