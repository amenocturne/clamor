export const scrollToFile = (fileIdx: number): void => {
	const el = document.querySelector(`[data-file-idx="${fileIdx}"]`);
	if (!el) return;
	el.scrollIntoView({ behavior: "smooth", block: "start" });
	el.classList.add("highlighted");
	setTimeout(() => el.classList.remove("highlighted"), 1200);
};
