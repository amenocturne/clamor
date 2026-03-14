import { h } from "snabbdom";
import type { VNode } from "snabbdom";
import type { FileDiff, Model, Msg } from "../../types.ts";
import { scrollToFile } from "../scroll.ts";

export const filterFiles = (
	files: readonly FileDiff[],
	query: string,
): { file: FileDiff; fileIdx: number }[] => {
	const items = files.map((file, idx) => ({ file, fileIdx: idx }));
	if (!query) return items;
	const lowerQuery = query.toLowerCase();
	return items.filter(({ file }) => file.path.toLowerCase().includes(lowerQuery));
};

export const fileSearchView = (model: Model, dispatch: (msg: Msg) => void): VNode | null => {
	if (!model.fileSearchOpen || !model.data) return null;

	const diffData = model.data.diffs[model.activeView];
	const files = diffData?.files ?? [];
	const filtered = filterFiles(files, model.fileSearchQuery);

	return h(
		"div.file-search-overlay",
		{
			on: {
				click: (e: Event) => {
					if ((e.target as HTMLElement).classList.contains("file-search-overlay")) {
						dispatch({ type: "closeFileSearch" });
					}
				},
			},
		},
		[
			h("div.file-search-dialog", [
				h("input.file-search-input", {
					props: {
						type: "text",
						placeholder: "Search files...",
						value: model.fileSearchQuery,
					},
					hook: {
						insert: (vnode) => {
							(vnode.elm as HTMLInputElement).focus();
						},
					},
					on: {
						input: (e: Event) => {
							const target = e.target as HTMLInputElement;
							dispatch({ type: "setFileSearchQuery", query: target.value });
						},
						keydown: (e: KeyboardEvent) => {
							if (e.key === "ArrowDown") {
								e.preventDefault();
								dispatch({ type: "fileSearchNavigate", direction: 1 });
							} else if (e.key === "ArrowUp") {
								e.preventDefault();
								dispatch({ type: "fileSearchNavigate", direction: -1 });
							} else if (e.key === "Enter") {
								e.preventDefault();
								const selected = filtered[model.fileSearchSelectedIdx];
								if (selected) {
									dispatch({ type: "closeFileSearch" });
									setTimeout(() => scrollToFile(selected.fileIdx), 50);
								}
							} else if (e.key === "Escape") {
								e.preventDefault();
								dispatch({ type: "closeFileSearch" });
							}
						},
					},
				}),
				h(
					"div.file-search-results",
					filtered.map(({ file, fileIdx }, idx) => {
						const pathParts = file.path.split("/");
						const filename = pathParts.pop() ?? file.path;
						const dir = pathParts.join("/");

						return h(
							"div.file-search-item",
							{
								class: { selected: idx === model.fileSearchSelectedIdx },
								on: {
									click: () => {
										dispatch({ type: "closeFileSearch" });
										setTimeout(() => scrollToFile(fileIdx), 50);
									},
								},
								hook:
									idx === model.fileSearchSelectedIdx
										? {
												update: (_, vnode) => {
													(vnode.elm as HTMLElement).scrollIntoView({ block: "nearest" });
												},
												insert: (vnode) => {
													(vnode.elm as HTMLElement).scrollIntoView({ block: "nearest" });
												},
											}
										: undefined,
							},
							[
								h("span.file-search-filename", filename),
								dir ? h("span.file-search-dir", dir) : null,
							].filter(Boolean) as VNode[],
						);
					}),
				),
				filtered.length === 0 ? h("div.file-search-empty", "No matching files") : null,
			]),
		],
	);
};
