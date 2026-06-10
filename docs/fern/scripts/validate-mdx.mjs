#!/usr/bin/env node
/**
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * MDX parse validation for every .mdx page under versions/.
 *
 * `fern check` validates configuration but does not surface MDX parse
 * errors — those only show up at dev-server reload time, one page at a
 * time. This script compiles every page with @mdx-js/mdx (the parser
 * Fern uses) and reports all failures in one pass.
 *
 * Run from the fern/ directory: `node scripts/validate-mdx.mjs`.
 * Wired into `npm run check` and CI.
 */

import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";

let compile;
try {
  ({ compile } = await import("@mdx-js/mdx"));
} catch {
  console.error(
    "validate-mdx: @mdx-js/mdx is not installed. Run `npm install` in fern/ first."
  );
  process.exit(2);
}

// docs/fern/ layout — walk parent (docs/) but skip docs/fern.
const ROOTS = [".."];
const SKIP_DIRS = new Set(["fern", "node_modules", ".git"]);

async function* walk(dir) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (SKIP_DIRS.has(entry.name)) continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(path);
    } else if (entry.name.endsWith(".mdx")) {
      yield path;
    }
  }
}

let failed = 0;
let total = 0;
for (const root of ROOTS) {
  for await (const file of walk(root)) {
    total += 1;
    try {
      const src = await readFile(file, "utf8");
      await compile(src, { format: "mdx" });
    } catch (err) {
      failed += 1;
      const msg = (err.message || String(err)).split("\n")[0];
      console.error(`\n${file}`);
      console.error(`  ${msg}`);
      if (err.line) console.error(`  at line ${err.line}, column ${err.column}`);
    }
  }
}

if (failed > 0) {
  console.error(`\n${failed}/${total} MDX files failed to parse`);
  process.exit(1);
}
console.log(`validate-mdx: ${total} files parsed cleanly`);
