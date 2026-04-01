import { basename } from "node:path";
import type { Commit, ReviewComment, ReviewSubmission } from "./types.ts";

const formatTimestamp = (): string => {
	const now = new Date();
	const pad = (n: number) => String(n).padStart(2, "0");
	return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
};

const formatCommitList = (commits: readonly Commit[]): string =>
	commits.map((c) => `${c.hash.slice(0, 7)} ${c.message}`).join(", ");

const formatLineRange = (comment: ReviewComment): string =>
	comment.startLine === comment.endLine
		? `Line ${comment.startLine}`
		: `Lines ${comment.startLine}-${comment.endLine}`;

const formatCodeBlock = (code: string): string =>
	code
		.split("\n")
		.map((line) => `    ${line}`)
		.join("\n");

const formatComment = (comment: ReviewComment): string => {
	const heading = `### ${formatLineRange(comment)}`;
	const code = formatCodeBlock(comment.code);
	const selected = comment.selectedText ? `\n\n> ${comment.selectedText}` : "";
	return `${heading}\n\n${code}${selected}\n\n${comment.text}`;
};

const groupByFile = (
	comments: readonly ReviewComment[],
): ReadonlyMap<string, readonly ReviewComment[]> => {
	const groups = new Map<string, ReviewComment[]>();
	for (const comment of comments) {
		const existing = groups.get(comment.file);
		if (existing) {
			existing.push(comment);
		} else {
			groups.set(comment.file, [comment]);
		}
	}
	return groups;
};

export const formatReview = (
	submission: ReviewSubmission,
	commits: readonly Commit[],
	range: string,
): string => {
	const lines: string[] = [];
	const timestamp = formatTimestamp();

	lines.push(`# Review: ${range}`);
	lines.push("");
	lines.push(`**Verdict:** ${submission.verdict}`);
	lines.push(`**Commits:** ${formatCommitList(commits)}`);
	lines.push(`**Reviewed:** ${timestamp}`);

	if (submission.comments.length === 0 && submission.summary.length === 0) {
		lines.push("");
		lines.push("No comments. Changes approved.");
		return `${lines.join("\n")}\n`;
	}

	if (submission.summary.length > 0) {
		lines.push("");
		lines.push("## Summary");
		lines.push("");
		lines.push(submission.summary);
	}

	const grouped = groupByFile(submission.comments);
	for (const [file, fileComments] of grouped) {
		lines.push("");
		lines.push(`## ${file}`);
		lines.push("");
		lines.push(fileComments.map(formatComment).join("\n\n"));
	}

	return `${lines.join("\n")}\n`;
};

export const formatAnnotation = (
	submission: ReviewSubmission,
	files: readonly string[],
): string => {
	const lines: string[] = [];
	const timestamp = formatTimestamp();
	const label = files.length === 1 ? basename(files[0]!) : `${files.length} files`;

	lines.push(`# Annotations: ${label}`);
	lines.push(`**Annotated:** ${timestamp}`);

	if (submission.summary.length > 0) {
		lines.push("");
		lines.push("## Summary");
		lines.push("");
		lines.push(submission.summary);
	}

	if (submission.comments.length > 0) {
		if (files.length > 1) {
			const grouped = groupByFile(submission.comments);
			for (const [file, fileComments] of grouped) {
				lines.push("");
				lines.push(`## ${file}`);
				lines.push("");
				lines.push(fileComments.map(formatComment).join("\n\n"));
			}
		} else {
			lines.push("");
			lines.push("## Annotations");
			lines.push("");
			lines.push(submission.comments.map(formatComment).join("\n\n"));
		}
	}

	return `${lines.join("\n")}\n`;
};
