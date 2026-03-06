import { h } from "snabbdom";
import type { VNode } from "snabbdom";
import type { Model, Msg } from "../../types.ts";

export const headerView = (model: Model, dispatch: (msg: Msg) => void): VNode =>
	h("div.header", [
		h("div", { style: { display: "flex", alignItems: "center", gap: "8px" } }, [
			h("button.sidebar-toggle.btn-ghost", {
				on: { click: () => dispatch({ type: "toggleSidebar" }) },
				attrs: { "aria-label": "Toggle sidebar" },
			}, "☰"),
			h("span.header-title", model.data?.project ? `Review: ${model.data.project}` : "Agent Review"),
		]),
		model.viewingPastReview
			? h("div.header-actions")
			: h("div.header-actions", [
				h("button.btn.btn-secondary", {
					on: { click: () => dispatch({ type: "submit", verdict: "approved" }) },
					attrs: { disabled: model.submitted, "aria-label": "Approve changes" },
				}, "Approve"),
				h("button.btn.btn-primary", {
					on: { click: () => dispatch({ type: "submit", verdict: "changes-requested" }) },
					attrs: { disabled: model.submitted, "aria-label": "Submit review with comments" },
				}, "Submit ▶"),
			]),
	]);
