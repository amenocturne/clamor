import { resolve, join, basename } from "node:path";
import { homedir } from "node:os";
import { mkdir, readdir, unlink } from "node:fs/promises";
import { parseDiff } from "./parser.ts";
import { formatReview } from "./formatter.ts";
import type { ApiData, Commit, DiffData } from "./types.ts";

// === CLI Parsing ===

type CliArgs = {
	readonly repo: string;
	readonly range: string;
	readonly message: string | null;
	readonly project: string | null;
	readonly saveDir: string;
	readonly port: number;
};

const USAGE = `Usage: bun run src/server.ts --repo <path> --range <range> [--message <text>] [--save-dir <path>] [--port <number>]`;

const parseArgs = (argv: readonly string[]): CliArgs => {
	const args = argv.slice(2);
	let repo: string | null = null;
	let range: string | null = null;
	let message: string | null = null;
	let project: string | null = null;
	let saveDir: string | null = null;
	let port = 0;

	for (let i = 0; i < args.length; i++) {
		const flag = args[i];
		const next = args[i + 1];
		switch (flag) {
			case "--repo":
				repo = next ?? null;
				i++;
				break;
			case "--range":
				range = next ?? null;
				i++;
				break;
			case "--message":
				message = next ?? null;
				i++;
				break;
			case "--project":
				project = next ?? null;
				i++;
				break;
			case "--save-dir":
				saveDir = next ?? null;
				i++;
				break;
			case "--port":
				port = Number.parseInt(next ?? "0", 10);
				i++;
				break;
		}
	}

	if (!repo || !range) {
		console.error(USAGE);
		process.exit(1);
	}

	return {
		repo: resolve(repo),
		range,
		message,
		project,
		saveDir: saveDir ? resolve(saveDir) : join(homedir(), ".claude", "reviews", basename(resolve(repo))),
		port,
	};
};

// === Git Helpers ===

const git = async (
	repo: string,
	args: readonly string[],
): Promise<string> => {
	const proc = Bun.spawn(["git", "-C", repo, ...args], {
		stdout: "pipe",
		stderr: "pipe",
	});
	await proc.exited;
	const stdout = await new Response(proc.stdout).text();
	if (proc.exitCode !== 0) {
		const stderr = await new Response(proc.stderr).text();
		throw new Error(stderr.trim());
	}
	return stdout.trim();
};

const validateRepo = async (repo: string): Promise<void> => {
	try {
		await git(repo, ["rev-parse", "--git-dir"]);
	} catch (e) {
		console.error(`Error: '${repo}' is not a git repository`);
		process.exit(1);
	}
};

const validateRange = async (
	repo: string,
	range: string,
): Promise<void> => {
	// rev-parse --verify works on single refs, not ranges like A..B
	// Validate each side of the range separately
	const parts = range.includes("..") ? range.split("..").filter(Boolean) : [range];
	for (const part of parts) {
		try {
			await git(repo, ["rev-parse", "--verify", part!]);
		} catch {
			console.error(`Error: ref '${part}' in range '${range}' does not resolve`);
			process.exit(1);
		}
	}
};

const getCommits = async (
	repo: string,
	range: string,
): Promise<readonly Commit[]> => {
	const raw = await git(repo, [
		"log",
		"--format=%H%n%s%n%ai",
		"--reverse",
		range,
	]);
	if (!raw) return [];
	const lines = raw.split("\n");
	const commits: Commit[] = [];
	for (let i = 0; i + 2 < lines.length; i += 3) {
		commits.push({
			hash: lines[i]!,
			message: lines[i + 1]!,
			date: lines[i + 2]!,
		});
	}
	return commits;
};

const getDiff = async (
	repo: string,
	range: string,
): Promise<DiffData> => {
	const raw = await git(repo, ["diff", "-U99999", "-M", range]);
	return { files: parseDiff(raw) };
};

const getCommitDiff = async (
	repo: string,
	hash: string,
): Promise<DiffData> => {
	const raw = await git(repo, [
		"diff",
		"-U99999",
		"-M",
		`${hash}^..${hash}`,
	]);
	return { files: parseDiff(raw) };
};

// === HTTP Server ===

const buildBundle = async (): Promise<string> => {
	const result = await Bun.build({
		entrypoints: [join(import.meta.dir, "frontend/main.ts")],
		minify: true,
	});
	if (!result.success) {
		throw new Error(
			`Build failed: ${result.logs.map((l) => l.message).join("\n")}`,
		);
	}
	return await result.outputs[0]!.text();
};

const startServer = (
	apiData: ApiData,
	args: CliArgs,
	bundledJs: string,
) => {
	const htmlPath = join(import.meta.dir, "../static/index.html");

	const server = Bun.serve({
		port: args.port,
		fetch: async (req) => {
			const url = new URL(req.url);

			if (req.method === "GET" && url.pathname === "/") {
				const html = await Bun.file(htmlPath).text();
				const injected = html.replace(
					"<!-- BUNDLE -->",
					'<script src="/bundle.js"></script>',
				);
				return new Response(injected, {
					headers: { "Content-Type": "text/html" },
				});
			}

			if (req.method === "GET" && url.pathname === "/bundle.js") {
				return new Response(bundledJs, {
					headers: { "Content-Type": "application/javascript" },
				});
			}

			if (req.method === "GET" && url.pathname === "/api/data") {
				return Response.json(apiData);
			}

			if (req.method === "POST" && url.pathname === "/api/submit") {
				const submission = await req.json();
				const commits = [...apiData.commits];
				const resolvedRange = commits.length > 0
					? `${commits[0]!.hash.slice(0, 7)}..${commits[commits.length - 1]!.hash.slice(0, 7)}`
					: args.range;
				const formatted = formatReview(
					submission,
					commits,
					resolvedRange,
				);

				await mkdir(args.saveDir, { recursive: true });

				const now = new Date();
				const pad = (n: number) => String(n).padStart(2, "0");
				const timestamp = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
				const filename = args.project ? `${timestamp}-${args.project}.md` : `${timestamp}.md`;
				const savePath = join(args.saveDir, filename);

				await Bun.write(savePath, formatted);
				console.error(`Review saved to ${savePath}`);

				setTimeout(() => process.exit(0), 500);
				return Response.json({ ok: true });
			}

			if (req.method === "GET" && url.pathname === "/api/reviews") {
				try {
					const files = await readdir(args.saveDir);
					const reviews = files
						.filter((f) => f.endsWith(".md"))
						.sort()
						.reverse()
						.map((f) => ({ filename: f }));
					return Response.json(reviews);
				} catch {
					return Response.json([]);
				}
			}

			if (req.method === "GET" && url.pathname.startsWith("/api/reviews/")) {
				const filename = decodeURIComponent(url.pathname.slice("/api/reviews/".length));
				try {
					const content = await Bun.file(join(args.saveDir, filename)).text();
					return Response.json({ content });
				} catch {
					return new Response("Not Found", { status: 404 });
				}
			}

			if (req.method === "DELETE" && url.pathname.startsWith("/api/reviews/")) {
				const filename = decodeURIComponent(url.pathname.slice("/api/reviews/".length));
				try {
					await unlink(join(args.saveDir, filename));
					return Response.json({ ok: true });
				} catch {
					return new Response("Not Found", { status: 404 });
				}
			}

			return new Response("Not Found", { status: 404 });
		},
	});

	return server;
};

// === Main ===

const main = async () => {
	const args = parseArgs(Bun.argv);

	await validateRepo(args.repo);
	await validateRange(args.repo, args.range);

	const commits = await getCommits(args.repo, args.range);
	const combinedDiff = await getDiff(args.repo, args.range);

	if (combinedDiff.files.length === 0 && commits.length === 0) {
		console.error("No changes in the specified range");
		process.exit(0);
	}

	const diffs: Record<string, DiffData> = { combined: combinedDiff };
	for (const commit of commits) {
		diffs[commit.hash] = await getCommitDiff(args.repo, commit.hash);
	}

	const apiData: ApiData = {
		commits,
		diffs,
		message: args.message,
		repo: args.repo,
		project: args.project,
	};

	const bundledJs = await buildBundle();

	const server = startServer(apiData, args, bundledJs);
	const port = server.port;

	console.error(`Review server running at http://localhost:${port}`);
	Bun.spawn(["open", `http://localhost:${port}`]);
};

process.on("SIGINT", () => {
	process.exit(1);
});

main();
