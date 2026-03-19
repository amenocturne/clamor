import { afterEach, beforeEach, describe, expect, it } from "bun:test";
import { formatReview } from "../src/formatter.ts";
import type { Commit, ReviewSubmission } from "../src/types.ts";

const FIXED_DATE = new Date("2025-01-15T10:30:45Z");

const commits: readonly Commit[] = [
	{ hash: "abc1234def5678", message: "Add feature X", date: "2025-01-14 09:00:00 +0000" },
	{ hash: "def5678abc1234", message: "Fix bug in Y", date: "2025-01-14 10:00:00 +0000" },
];

describe("formatReview", () => {
	let originalDate: DateConstructor;

	beforeEach(() => {
		originalDate = globalThis.Date;
		// Replace Date so new Date() returns fixed time, but preserve other Date functionality
		const FixedDate = ((...args: unknown[]) => {
			if (args.length === 0) {
				return new originalDate(FIXED_DATE);
			}
			// @ts-ignore
			return new originalDate(...args);
		}) as unknown as DateConstructor;
		FixedDate.prototype = originalDate.prototype;
		FixedDate.now = () => FIXED_DATE.getTime();
		FixedDate.parse = originalDate.parse;
		FixedDate.UTC = originalDate.UTC;
		globalThis.Date = FixedDate;
	});

	afterEach(() => {
		globalThis.Date = originalDate;
	});

	it("formats changes-requested with comments", () => {
		const submission: ReviewSubmission = {
			verdict: "changes-requested",
			summary: "Several issues found.",
			comments: [
				{
					file: "src/app.ts",
					startLine: 10,
					endLine: 15,
					type: "fix",
					text: "This logic is broken.",
					code: "const x = 1;\nconst y = 2;",
				},
			],
		};

		const result = formatReview(submission, commits, "HEAD~2..HEAD");

		expect(result).toContain("# Review: HEAD~2..HEAD");
		expect(result).toContain("**Verdict:** changes-requested");
		expect(result).toContain("**Commits:** abc1234 Add feature X, def5678 Fix bug in Y");
		expect(result).toContain("**Reviewed:** 2025-01-15");
		expect(result).toContain("## Summary");
		expect(result).toContain("Several issues found.");
		expect(result).toContain("## src/app.ts");
		expect(result).toContain("### Lines 10-15 [fix]");
		expect(result).toContain("This logic is broken.");
	});

	it("formats approved review", () => {
		const submission: ReviewSubmission = {
			verdict: "approved",
			summary: "",
			comments: [],
		};

		const result = formatReview(submission, commits, "HEAD~2..HEAD");

		expect(result).toContain("# Review: HEAD~2..HEAD");
		expect(result).toContain("**Verdict:** approved");
		expect(result).toContain("No comments. Changes approved.");
		expect(result).not.toContain("## Summary");
	});

	it("uses 'Line N' for single-line comment", () => {
		const submission: ReviewSubmission = {
			verdict: "changes-requested",
			summary: "",
			comments: [
				{
					file: "src/utils.ts",
					startLine: 42,
					endLine: 42,
					type: "suggestion",
					text: "Consider renaming.",
					code: "const foo = bar;",
				},
			],
		};

		const result = formatReview(submission, commits, "HEAD~1..HEAD");

		expect(result).toContain("### Line 42 [suggestion]");
		expect(result).not.toContain("Lines 42-42");
	});

	it("uses 'Lines N-M' for multi-line comment", () => {
		const submission: ReviewSubmission = {
			verdict: "changes-requested",
			summary: "",
			comments: [
				{
					file: "src/utils.ts",
					startLine: 10,
					endLine: 20,
					type: "question",
					text: "Why is this here?",
					code: "line1\nline2",
				},
			],
		};

		const result = formatReview(submission, commits, "HEAD~1..HEAD");

		expect(result).toContain("### Lines 10-20 [question]");
	});

	it("groups comments by file", () => {
		const submission: ReviewSubmission = {
			verdict: "changes-requested",
			summary: "",
			comments: [
				{
					file: "src/a.ts",
					startLine: 1,
					endLine: 1,
					type: "fix",
					text: "Fix A1.",
					code: "a1",
				},
				{
					file: "src/b.ts",
					startLine: 5,
					endLine: 5,
					type: "fix",
					text: "Fix B.",
					code: "b1",
				},
				{
					file: "src/a.ts",
					startLine: 10,
					endLine: 10,
					type: "suggestion",
					text: "Fix A2.",
					code: "a2",
				},
			],
		};

		const result = formatReview(submission, commits, "HEAD~1..HEAD");

		const aIndex = result.indexOf("## src/a.ts");
		const bIndex = result.indexOf("## src/b.ts");
		expect(aIndex).toBeGreaterThan(-1);
		expect(bIndex).toBeGreaterThan(-1);
		expect(aIndex).toBeLessThan(bIndex);

		// Both comments for src/a.ts appear before src/b.ts section
		const fixA1 = result.indexOf("Fix A1.");
		const fixA2 = result.indexOf("Fix A2.");
		expect(fixA1).toBeGreaterThan(aIndex);
		expect(fixA2).toBeGreaterThan(aIndex);
		expect(fixA2).toBeLessThan(bIndex);
	});

	it("omits Summary section when summary is empty", () => {
		const submission: ReviewSubmission = {
			verdict: "changes-requested",
			summary: "",
			comments: [
				{
					file: "src/x.ts",
					startLine: 1,
					endLine: 1,
					type: "fix",
					text: "Issue.",
					code: "x",
				},
			],
		};

		const result = formatReview(submission, commits, "HEAD~1..HEAD");

		expect(result).not.toContain("## Summary");
	});

	it("uses 4-space indent for code blocks", () => {
		const submission: ReviewSubmission = {
			verdict: "changes-requested",
			summary: "",
			comments: [
				{
					file: "src/x.ts",
					startLine: 1,
					endLine: 3,
					type: "fix",
					text: "Bad code.",
					code: "const a = 1;\nconst b = 2;\nconst c = 3;",
				},
			],
		};

		const result = formatReview(submission, commits, "HEAD~1..HEAD");

		expect(result).toContain("    const a = 1;\n    const b = 2;\n    const c = 3;");
		// No fenced code blocks
		expect(result).not.toContain("```");
	});
});
