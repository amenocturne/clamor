import { h } from "snabbdom";
import type { VNode } from "snabbdom";
import type { Model, Msg } from "../../types.ts";
import { diffAreaView } from "./diff.ts";
import { headerView } from "./header.ts";
import { sidebarView } from "./sidebar.ts";

let showRawMarkdown = false;

const escapeHtml = (s: string): string =>
	s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const renderMarkdown = (md: string): string => {
	const lines = md.split("\n");
	const html: string[] = [];
	let inCode = false;
	let inList = false;

	for (let i = 0; i < lines.length; i++) {
		const line = lines[i]!;

		// Indented code block (4 spaces)
		if (line.startsWith("    ") && !inCode) {
			inCode = true;
			html.push("<pre><code>");
		}
		if (inCode) {
			if (!line.startsWith("    ") && line.trim() !== "") {
				inCode = false;
				html.push("</code></pre>");
			} else {
				html.push(escapeHtml(line.slice(4)));
				continue;
			}
		}

		// Empty line
		if (line.trim() === "") {
			if (inList) {
				html.push("</ul>");
				inList = false;
			}
			continue;
		}

		// Headings
		const headingMatch = line.match(/^(#{1,3})\s+(.*)/);
		if (headingMatch) {
			const level = headingMatch[1]!.length;
			html.push(`<h${level}>${inlineFormat(escapeHtml(headingMatch[2]!))}</h${level}>`);
			continue;
		}

		// List items
		if (line.startsWith("- ")) {
			if (!inList) {
				html.push("<ul>");
				inList = true;
			}
			html.push(`<li>${inlineFormat(escapeHtml(line.slice(2)))}</li>`);
			continue;
		}

		// Paragraph
		html.push(`<p>${inlineFormat(escapeHtml(line))}</p>`);
	}

	if (inCode) html.push("</code></pre>");
	if (inList) html.push("</ul>");

	return html.join("\n");
};

const inlineFormat = (s: string): string =>
	s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`(.+?)`/g, "<code>$1</code>");

export const rootView = (model: Model, dispatch: (msg: Msg) => void): VNode => {
	if (model.error) {
		return h("div.app", [h("div.empty-state", `Error: ${model.error}`)]);
	}

	if (!model.data) {
		return h("div.app", [h("div.loading", "Loading diff data...")]);
	}

	const mainContent = model.viewingPastReview
		? h("div.past-review-content", [
				h("div.past-review-toolbar", [
					h(
						"button.btn.btn-secondary.past-review-back",
						{
							on: { click: () => dispatch({ type: "closePastReview" }) },
						},
						"\u2190 Back to review",
					),
					h(
						"button.btn.btn-ghost",
						{
							on: {
								click: (e: Event) => {
									showRawMarkdown = !showRawMarkdown;
									const btn = e.target as HTMLElement;
									btn.textContent = showRawMarkdown ? "Rendered" : "Raw";
									const container = btn.closest(".past-review-content");
									const rendered = container?.querySelector(
										".past-review-rendered",
									) as HTMLElement | null;
									const raw = container?.querySelector(".past-review-raw") as HTMLElement | null;
									if (rendered && raw) {
										rendered.style.display = showRawMarkdown ? "none" : "block";
										raw.style.display = showRawMarkdown ? "block" : "none";
									}
								},
							},
						},
						"Raw",
					),
				]),
				h("div.past-review-rendered", {
					style: { display: showRawMarkdown ? "none" : "block" },
					hook: {
						insert: (vnode) => {
							(vnode.elm as HTMLElement).innerHTML = renderMarkdown(model.viewingPastReview!);
						},
						update: (_, vnode) => {
							(vnode.elm as HTMLElement).innerHTML = renderMarkdown(model.viewingPastReview!);
						},
					},
				}),
				h(
					"pre.past-review-raw",
					{
						style: { display: showRawMarkdown ? "block" : "none" },
					},
					model.viewingPastReview,
				),
			])
		: diffAreaView(model, dispatch);

	return h("div.app", [
		headerView(model, dispatch),
		h("div.main", [sidebarView(model, dispatch), mainContent]),
	]);
};
