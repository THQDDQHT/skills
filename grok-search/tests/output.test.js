#!/usr/bin/env node
import assert from "node:assert/strict";
import { mkdtemp, readFile, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { writeFullOutput } from "../scripts/lib/output.js";

const outputDir = await mkdtemp(path.join(tmpdir(), "grok-search-output-test-"));
const config = { outputDir, outputRetentionDays: 30 };

// CJK labels all slug to the same fallback; parallel writes in the same second
// must still land in distinct files.
const [first, second] = await Promise.all([
  writeFullOutput(config, { kind: "sources", provider: "search", label: "中文查询一", content: "one" }),
  writeFullOutput(config, { kind: "sources", provider: "search", label: "中文查询二", content: "two" }),
]);
assert.notEqual(first, second);
assert.equal(await readFile(first, "utf8"), "one");
assert.equal(await readFile(second, "utf8"), "two");

assert.equal((await stat(first)).mode & 0o777, 0o600);
assert.equal((await stat(second)).mode & 0o777, 0o600);

console.log("output fixtures ok");
