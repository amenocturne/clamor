import { h } from "snabbdom";
import type { VNode } from "snabbdom";
import type { Msg, StoredComment } from "../../types.ts";

export const savedCommentView = (comment: StoredComment, dispatch: (msg: Msg) => void): VNode =>
	h("tr.comment-box-row", [
		h("td", { attrs: { colspan: 3 } }, [
			h(`div.saved-comment.${comment.type}`, {
				on: { click: () => dispatch({ type: "editComment", id: comment.id }) },
			}, [
				h("div.saved-comment-header", [
					h(`span.saved-comment-severity.${comment.type}`, comment.type.toUpperCase()),
					h("span.saved-comment-location", `${comment.file}:${comment.startLine}`),
				]),
				h("div", comment.text),
			]),
		]),
	]);
