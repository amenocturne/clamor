import { h } from "snabbdom";
import type { VNode } from "snabbdom";
import type { FileDiff, Model, Msg } from "../../types.ts";
import { scrollToFile } from "../scroll.ts";

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

// --- Tree Building ---

type TreeNode = {
	name: string;
	fullPath: string;
	children: TreeNode[];
	fileIdx?: number;
	stats?: { added: number; deleted: number };
};

const buildTree = (files: readonly FileDiff[]): TreeNode => {
	const root: TreeNode = { name: "", fullPath: "", children: [] };

	for (let i = 0; i < files.length; i++) {
		const file = files[i]!;
		const parts = file.path.split("/");
		let current = root;

		for (let j = 0; j < parts.length; j++) {
			const part = parts[j]!;
			const isFile = j === parts.length - 1;
			const fullPath = parts.slice(0, j + 1).join("/");

			if (isFile) {
				current.children.push({
					name: part,
					fullPath,
					children: [],
					fileIdx: i,
					stats: fileStats(file),
				});
			} else {
				let dir = current.children.find((c) => c.name === part && c.fileIdx === undefined);
				if (!dir) {
					dir = { name: part, fullPath, children: [] };
					current.children.push(dir);
				}
				current = dir;
			}
		}
	}

	compactTree(root);
	return root;
};

// Merge single-child directory chains: src/ -> main/ -> java/ becomes src/main/java/
const compactTree = (node: TreeNode): void => {
	for (let i = 0; i < node.children.length; i++) {
		let child = node.children[i]!;

		while (
			child.fileIdx === undefined &&
			child.children.length === 1 &&
			child.children[0]!.fileIdx === undefined
		) {
			const grandchild = child.children[0]!;
			child = {
				name: `${child.name}/${grandchild.name}`,
				fullPath: grandchild.fullPath,
				children: grandchild.children,
			};
		}

		node.children[i] = child;
		compactTree(child);
	}
};

const renderTreeNodes = (
	node: TreeNode,
	depth: number,
	collapsedDirs: ReadonlySet<string>,
	dispatch: (msg: Msg) => void,
): VNode[] => {
	const result: VNode[] = [];
	const dirs = node.children.filter((c) => c.fileIdx === undefined);
	const files = node.children.filter((c) => c.fileIdx !== undefined);

	for (const dir of dirs) {
		const isCollapsed = collapsedDirs.has(dir.fullPath);
		result.push(
			h(
				"div.file-tree-dir",
				{
					style: { paddingLeft: `${depth * 12 + 8}px` },
					on: { click: () => dispatch({ type: "toggleDir", path: dir.fullPath }) },
				},
				[h("span.file-tree-chevron", isCollapsed ? "\u25B8" : "\u25BE"), h("span", dir.name)],
			),
		);
		if (!isCollapsed) {
			result.push(...renderTreeNodes(dir, depth + 1, collapsedDirs, dispatch));
		}
	}

	for (const file of files) {
		result.push(
			h(
				"div.file-tree-file",
				{
					style: { paddingLeft: `${depth * 12 + 8}px` },
					on: { click: () => scrollToFile(file.fileIdx!) },
				},
				[
					h("span", file.name),
					h(
						"span.file-stats",
						[
							file.stats!.added > 0 ? h("span.file-stats-add", `+${file.stats!.added}`) : null,
							file.stats!.added > 0 && file.stats!.deleted > 0 ? " " : null,
							file.stats!.deleted > 0 ? h("span.file-stats-del", `-${file.stats!.deleted}`) : null,
						].filter(Boolean) as VNode[],
					),
				],
			),
		);
	}

	return result;
};

// --- Sections ---

const commitsSection = (model: Model, dispatch: (msg: Msg) => void): VNode => {
	const data = model.data!;
	const items: VNode[] = [
		h(
			"div.commit-item",
			{
				class: { active: model.activeView === "combined" },
				on: { click: () => dispatch({ type: "setActiveView", view: "combined" }) },
			},
			[
				h("span.commit-radio"),
				h("span.commit-msg", { attrs: { title: "All changes" } }, "All changes"),
			],
		),
	];

	for (const commit of data.commits) {
		items.push(
			h(
				"div.commit-item",
				{
					class: { active: model.activeView === commit.hash },
					on: { click: () => dispatch({ type: "setActiveView", view: commit.hash }) },
				},
				[
					h("span.commit-radio"),
					h("span.commit-hash", commit.hash.slice(0, 7)),
					h("span.commit-msg", { attrs: { title: commit.message } }, commit.message),
				],
			),
		);
	}

	return h("div.sidebar-section", [h("div.sidebar-label", "Commits"), ...items]);
};

const filesSection = (model: Model, dispatch: (msg: Msg) => void): VNode => {
	const data = model.data!;
	const diffData = data.diffs[model.activeView];
	const files = diffData?.files ?? [];
	const tree = buildTree(files);

	return h("div.sidebar-section", [
		h("div.sidebar-label", `Files (${files.length})`),
		...renderTreeNodes(tree, 0, model.collapsedDirs, dispatch),
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
			const location =
				comment.startLine === comment.endLine
					? `${comment.file.split("/").pop()}:${comment.startLine}`
					: `${comment.file.split("/").pop()}:${comment.startLine}-${comment.endLine}`;

			return h(
				"div.comment-list-item",
				{
					class: { dimmed: !isVisible },
					on: {
						click: () => {
							const commentEl = document.querySelector(`[data-comment-id="${comment.id}"]`);
							if (commentEl) {
								commentEl.scrollIntoView({ behavior: "smooth", block: "center" });
							}
						},
					},
				},
				[h("span.comment-dot"), h("span", location)],
			);
		}),
	]);
};

const pastReviewsSection = (model: Model, dispatch: (msg: Msg) => void): VNode | null => {
	if (model.pastReviews.length === 0) return null;
	const label = model.data?.mode === "annotate" ? "Past Annotations" : "Past Reviews";

	return h("div.sidebar-section", [
		h("div.sidebar-label", label),
		...model.pastReviews.map((review) => {
			const name = review.filename.replace(/\.md$/, "");
			return h("div.past-review-item", [
				h(
					"span.past-review-name",
					{
						on: { click: () => dispatch({ type: "fetchPastReview", filename: review.filename }) },
					},
					name,
				),
				h(
					"button.btn-delete-review",
					{
						attrs: { "aria-label": `Delete review ${name}` },
						on: {
							click: (e: Event) => {
								e.stopPropagation();
								if (confirm("Delete this review?")) {
									dispatch({ type: "deletePastReview", filename: review.filename });
								}
							},
						},
					},
					"\u00D7",
				),
			]);
		}),
	]);
};

export const sidebarView = (model: Model, dispatch: (msg: Msg) => void): VNode => {
	const isAnnotate = model.data?.mode === "annotate";
	const sections: (VNode | null)[] = [
		isAnnotate ? null : commitsSection(model, dispatch),
		filesSection(model, dispatch),
		descriptionSection(model),
		summarySection(model, dispatch),
		commentsSection(model),
		pastReviewsSection(model, dispatch),
	];

	const width = model.sidebarWidth;
	return h(
		"div.sidebar",
		{
			class: { hidden: !model.sidebarOpen },
			hook: {
				insert: (vnode) => {
					(vnode.elm as HTMLElement).style.setProperty("--sidebar-width", `${width}px`);
				},
				update: (_old, vnode) => {
					(vnode.elm as HTMLElement).style.setProperty("--sidebar-width", `${width}px`);
				},
			},
		},
		sections.filter(Boolean) as VNode[],
	);
};
