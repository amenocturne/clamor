import type { ApiData, PastReviewMeta } from "../types.ts";
import { dispatch, startApp } from "./app.ts";

const fetchData = async (): Promise<void> => {
	try {
		const res = await fetch("/api/data");
		const data: ApiData = await res.json();
		if (data.project) document.title = `Review: ${data.project}`;
		dispatch({ type: "dataLoaded", data });
	} catch (e) {
		dispatch({ type: "dataError", error: String(e) });
	}

	try {
		const res = await fetch("/api/reviews");
		const reviews: PastReviewMeta[] = await res.json();
		dispatch({ type: "pastReviewsLoaded", reviews });
	} catch {}
};

startApp(fetchData);
