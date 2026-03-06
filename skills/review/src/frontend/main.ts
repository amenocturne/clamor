import type { ApiData } from "../types.ts";
import { dispatch, startApp } from "./app.ts";

const fetchData = async (): Promise<void> => {
	try {
		const res = await fetch("/api/data");
		const data: ApiData = await res.json();
		dispatch({ type: "dataLoaded", data });
	} catch (e) {
		dispatch({ type: "dataError", error: String(e) });
	}
};

startApp(fetchData);
