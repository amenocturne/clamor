import { h } from "snabbdom";
import type { VNode } from "snabbdom";
import type { Model, Msg } from "../../types.ts";
import { headerView } from "./header.ts";
import { sidebarView } from "./sidebar.ts";
import { diffAreaView } from "./diff.ts";

export const rootView = (model: Model, dispatch: (msg: Msg) => void): VNode => {
	if (model.error) {
		return h("div.app", [
			h("div.empty-state", `Error: ${model.error}`),
		]);
	}

	if (!model.data) {
		return h("div.app", [
			h("div.loading", "Loading diff data..."),
		]);
	}

	return h("div.app", [
		headerView(model, dispatch),
		h("div.main", [
			sidebarView(model, dispatch),
			diffAreaView(model, dispatch),
		]),
	]);
};
