import { init, classModule, propsModule, styleModule, eventListenersModule, attributesModule } from "snabbdom";
import type { VNode } from "snabbdom";
import type { Model, Msg, ReviewSubmission } from "../types.ts";
import { initialModel } from "./model.ts";
import { update } from "./update.ts";
import { rootView } from "./view/root.ts";

const patch = init([classModule, propsModule, styleModule, eventListenersModule, attributesModule]);

let model: Model = initialModel;
let vnode: VNode | Element = document.getElementById("app")!;

const dispatch = (msg: Msg): void => {
	const prev = model;
	model = update(model, msg);

	if (msg.type === "submit" && !prev.submitted) {
		const submission: ReviewSubmission = {
			verdict: msg.verdict,
			summary: model.summary,
			comments: [...model.comments],
		};
		fetch("/api/submit", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(submission),
		});
	}

	render();
};

const render = (): void => {
	const newVnode = rootView(model, dispatch);
	vnode = patch(vnode, newVnode);
};

export const startApp = (fetchData: () => Promise<void>): void => {
	render();
	fetchData();
};

export { dispatch, render };
