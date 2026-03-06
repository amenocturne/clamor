import { describe, expect, test } from "bun:test";
import { detectLanguage, parseDiff } from "../src/parser.ts";

describe("parseDiff", () => {
	test("single file, single hunk — basic add/delete/context", () => {
		const raw = `diff --git a/src/main.ts b/src/main.ts
index abc1234..def5678 100644
--- a/src/main.ts
+++ b/src/main.ts
@@ -1,5 +1,5 @@
 import { run } from "./app";

-const port = 3000;
+const port = 8080;

 run(port);
`;
		const files = parseDiff(raw);
		expect(files).toHaveLength(1);
		const file = files[0]!;
		expect(file.path).toBe("src/main.ts");
		expect(file.language).toBe("typescript");
		expect(file.binary).toBe(false);
		expect(file.truncated).toBe(false);
		expect(file.oldPath).toBeUndefined();
		expect(file.hunks).toHaveLength(1);

		const hunk = file.hunks[0]!;
		expect(hunk.oldStart).toBe(1);
		expect(hunk.newStart).toBe(1);
		expect(hunk.lines).toHaveLength(6);

		// context line
		expect(hunk.lines[0]).toEqual({
			type: "context",
			oldNum: 1,
			newNum: 1,
			content: "import { run } from \"./app\";",
		});
		// empty context line
		expect(hunk.lines[1]).toEqual({
			type: "context",
			oldNum: 2,
			newNum: 2,
			content: "",
		});
		// delete line
		expect(hunk.lines[2]).toEqual({
			type: "delete",
			oldNum: 3,
			newNum: null,
			content: "const port = 3000;",
		});
		// add line
		expect(hunk.lines[3]).toEqual({
			type: "add",
			oldNum: null,
			newNum: 3,
			content: "const port = 8080;",
		});
		// empty context line
		expect(hunk.lines[4]).toEqual({
			type: "context",
			oldNum: 4,
			newNum: 4,
			content: "",
		});
		// trailing context
		expect(hunk.lines[5]).toEqual({
			type: "context",
			oldNum: 5,
			newNum: 5,
			content: "run(port);",
		});
	});

	test("multi-file diff — correctly splits and parses multiple files", () => {
		const raw = `diff --git a/src/a.ts b/src/a.ts
index 1111111..2222222 100644
--- a/src/a.ts
+++ b/src/a.ts
@@ -1,3 +1,3 @@
 const x = 1;
-const y = 2;
+const y = 3;
 const z = 4;
diff --git a/src/b.py b/src/b.py
index 3333333..4444444 100644
--- a/src/b.py
+++ b/src/b.py
@@ -1,2 +1,3 @@
 def hello():
-    pass
+    print("hello")
+    return True
`;
		const files = parseDiff(raw);
		expect(files).toHaveLength(2);
		expect(files[0]!.path).toBe("src/a.ts");
		expect(files[0]!.language).toBe("typescript");
		expect(files[1]!.path).toBe("src/b.py");
		expect(files[1]!.language).toBe("python");
		expect(files[1]!.hunks[0]!.lines).toHaveLength(4);
	});

	test("rename detection — rename from/to populates oldPath", () => {
		const raw = `diff --git a/old/file.ts b/new/file.ts
similarity index 95%
rename from old/file.ts
rename to new/file.ts
index aaa1111..bbb2222 100644
--- a/old/file.ts
+++ b/new/file.ts
@@ -1,3 +1,3 @@
 export const name = "test";
-export const version = 1;
+export const version = 2;
 export const active = true;
`;
		const files = parseDiff(raw);
		expect(files).toHaveLength(1);
		const file = files[0]!;
		expect(file.path).toBe("new/file.ts");
		expect(file.oldPath).toBe("old/file.ts");
		expect(file.hunks).toHaveLength(1);
	});

	test("rename detection — different --- and +++ paths without rename lines", () => {
		const raw = `diff --git a/alpha.js b/beta.js
index aaa1111..bbb2222 100644
--- a/alpha.js
+++ b/beta.js
@@ -1,2 +1,2 @@
-const a = 1;
+const b = 1;
 module.exports = {};
`;
		const files = parseDiff(raw);
		expect(files).toHaveLength(1);
		expect(files[0]!.path).toBe("beta.js");
		expect(files[0]!.oldPath).toBe("alpha.js");
	});

	test("binary file — detected, binary=true, no hunks", () => {
		const raw = `diff --git a/image.png b/image.png
index 1234567..abcdefg 100644
Binary files a/image.png and b/image.png differ
`;
		const files = parseDiff(raw);
		expect(files).toHaveLength(1);
		const file = files[0]!;
		expect(file.binary).toBe(true);
		expect(file.hunks).toHaveLength(0);
		expect(file.path).toBe("image.png");
	});

	test("empty diff — returns empty array", () => {
		expect(parseDiff("")).toEqual([]);
		expect(parseDiff("   \n\n  ")).toEqual([]);
	});

	test("multiple hunks — correct line numbering across hunk boundaries", () => {
		const raw = `diff --git a/app.rs b/app.rs
index 1111111..2222222 100644
--- a/app.rs
+++ b/app.rs
@@ -1,4 +1,4 @@
 fn main() {
-    println!("old");
+    println!("new");
     let x = 1;
 }
@@ -10,4 +10,5 @@
 fn helper() {
     let a = 2;
+    let b = 3;
     let c = 4;
 }
`;
		const files = parseDiff(raw);
		expect(files).toHaveLength(1);
		const file = files[0]!;
		expect(file.language).toBe("rust");
		expect(file.hunks).toHaveLength(2);

		// First hunk: context, delete, add, context, context (closing brace)
		const h1 = file.hunks[0]!;
		expect(h1.oldStart).toBe(1);
		expect(h1.newStart).toBe(1);
		expect(h1.lines).toHaveLength(5);

		// Second hunk — numbering resets based on header
		const h2 = file.hunks[1]!;
		expect(h2.oldStart).toBe(10);
		expect(h2.newStart).toBe(10);
		expect(h2.lines).toHaveLength(5);

		// First line of second hunk
		expect(h2.lines[0]).toEqual({
			type: "context",
			oldNum: 10,
			newNum: 10,
			content: "fn helper() {",
		});
		// context
		expect(h2.lines[1]).toEqual({
			type: "context",
			oldNum: 11,
			newNum: 11,
			content: "    let a = 2;",
		});
		// added line
		expect(h2.lines[2]).toEqual({
			type: "add",
			oldNum: null,
			newNum: 12,
			content: "    let b = 3;",
		});
		// context after add — old still at 12, new at 13
		expect(h2.lines[3]).toEqual({
			type: "context",
			oldNum: 12,
			newNum: 13,
			content: "    let c = 4;",
		});
		// closing brace
		expect(h2.lines[4]).toEqual({
			type: "context",
			oldNum: 13,
			newNum: 14,
			content: "}",
		});
	});

	test("context line numbering — both oldNum and newNum increment", () => {
		const raw = `diff --git a/file.go b/file.go
index 1111111..2222222 100644
--- a/file.go
+++ b/file.go
@@ -5,4 +5,4 @@
 line five
 line six
 line seven
 line eight
`;
		const files = parseDiff(raw);
		const lines = files[0]!.hunks[0]!.lines;
		expect(lines[0]).toEqual({ type: "context", oldNum: 5, newNum: 5, content: "line five" });
		expect(lines[1]).toEqual({ type: "context", oldNum: 6, newNum: 6, content: "line six" });
		expect(lines[2]).toEqual({ type: "context", oldNum: 7, newNum: 7, content: "line seven" });
		expect(lines[3]).toEqual({ type: "context", oldNum: 8, newNum: 8, content: "line eight" });
	});

	test("add-only line — oldNum is null", () => {
		const raw = `diff --git a/file.ts b/file.ts
index 1111111..2222222 100644
--- a/file.ts
+++ b/file.ts
@@ -1,2 +1,3 @@
 const a = 1;
+const b = 2;
 const c = 3;
`;
		const files = parseDiff(raw);
		const lines = files[0]!.hunks[0]!.lines;
		expect(lines[1]).toEqual({
			type: "add",
			oldNum: null,
			newNum: 2,
			content: "const b = 2;",
		});
		// context after the add
		expect(lines[2]).toEqual({
			type: "context",
			oldNum: 2,
			newNum: 3,
			content: "const c = 3;",
		});
	});

	test("delete-only line — newNum is null", () => {
		const raw = `diff --git a/file.ts b/file.ts
index 1111111..2222222 100644
--- a/file.ts
+++ b/file.ts
@@ -1,3 +1,2 @@
 const a = 1;
-const b = 2;
 const c = 3;
`;
		const files = parseDiff(raw);
		const lines = files[0]!.hunks[0]!.lines;
		expect(lines[1]).toEqual({
			type: "delete",
			oldNum: 2,
			newNum: null,
			content: "const b = 2;",
		});
		// context after the delete
		expect(lines[2]).toEqual({
			type: "context",
			oldNum: 3,
			newNum: 2,
			content: "const c = 3;",
		});
	});

	test("no newline at end of file — marker lines are skipped", () => {
		const raw = `diff --git a/file.ts b/file.ts
index 1111111..2222222 100644
--- a/file.ts
+++ b/file.ts
@@ -1,3 +1,3 @@
 const a = 1;
-const b = 2;
\\ No newline at end of file
+const b = 3;
\\ No newline at end of file
`;
		const files = parseDiff(raw);
		const lines = files[0]!.hunks[0]!.lines;
		// Should have 3 lines: context, delete, add — the backslash lines are skipped
		expect(lines).toHaveLength(3);
		expect(lines[0]!.type).toBe("context");
		expect(lines[1]!.type).toBe("delete");
		expect(lines[2]!.type).toBe("add");
	});

	test("new file (--- /dev/null)", () => {
		const raw = `diff --git a/new.ts b/new.ts
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/new.ts
@@ -0,0 +1,3 @@
+const x = 1;
+const y = 2;
+const z = 3;
`;
		const files = parseDiff(raw);
		expect(files).toHaveLength(1);
		const file = files[0]!;
		expect(file.path).toBe("new.ts");
		expect(file.oldPath).toBeUndefined();
		expect(file.hunks[0]!.lines).toHaveLength(3);
		expect(file.hunks[0]!.lines.every((l) => l.type === "add")).toBe(true);
	});

	test("deleted file (+++ /dev/null)", () => {
		const raw = `diff --git a/old.ts b/old.ts
deleted file mode 100644
index 1234567..0000000
--- a/old.ts
+++ /dev/null
@@ -1,3 +0,0 @@
-const x = 1;
-const y = 2;
-const z = 3;
`;
		const files = parseDiff(raw);
		expect(files).toHaveLength(1);
		const file = files[0]!;
		expect(file.path).toBe("old.ts");
		expect(file.hunks[0]!.lines).toHaveLength(3);
		expect(file.hunks[0]!.lines.every((l) => l.type === "delete")).toBe(true);
	});
});

describe("detectLanguage", () => {
	test("maps common extensions correctly", () => {
		const cases: [string, string][] = [
			["src/app.ts", "typescript"],
			["main.tsx", "typescript"],
			["index.js", "javascript"],
			["app.jsx", "javascript"],
			["script.py", "python"],
			["lib.rs", "rust"],
			["main.go", "go"],
			["Module.hs", "haskell"],
			["App.java", "java"],
			["gem.rb", "ruby"],
			["style.css", "css"],
			["index.html", "html"],
			["data.json", "json"],
			["README.md", "markdown"],
			["config.yaml", "yaml"],
			["config.yml", "yaml"],
			["Cargo.toml", "toml"],
			["run.sh", "bash"],
			["query.sql", "sql"],
			["main.c", "c"],
			["main.cpp", "cpp"],
			["header.h", "c"],
			["header.hpp", "cpp"],
			["App.swift", "swift"],
			["Main.kt", "kotlin"],
			["App.scala", "scala"],
			["server.ex", "elixir"],
			["test.exs", "elixir"],
			["build.zig", "zig"],
		];
		for (const [path, expected] of cases) {
			expect(detectLanguage(path)).toBe(expected);
		}
	});

	test("unknown extension returns plaintext", () => {
		expect(detectLanguage("Makefile")).toBe("plaintext");
		expect(detectLanguage("file.xyz")).toBe("plaintext");
		expect(detectLanguage(".gitignore")).toBe("plaintext");
	});
});
