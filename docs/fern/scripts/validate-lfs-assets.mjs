#!/usr/bin/env node
/**
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Fail fast when docs assets are still Git LFS pointer files.
 *
 * Fern can publish a pointer file successfully because it is a small text file
 * with HTTP 200 semantics. Checkouts that build or preview docs must smudge LFS
 * objects before upload so rendered pages receive the binary asset bodies.
 */

import { open, readdir } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const docsRoot = resolve(scriptDir, "..", "..");
const skipDirs = new Set(["generated", "node_modules", ".git"]);
const assetExtensions = new Set([
  ".gif",
  ".ico",
  ".jpeg",
  ".jpg",
  ".mp4",
  ".png",
  ".svg",
  ".webp",
]);
const pointerPrefix = "version https://git-lfs.github.com/spec/v1";

function extensionFor(path) {
  const match = /(\.[^.\/]+)$/.exec(path);
  return match ? match[1].toLowerCase() : "";
}

async function* walk(dir) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch {
    return;
  }

  for (const entry of entries) {
    if (skipDirs.has(entry.name)) continue;
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(path);
    } else if (assetExtensions.has(extensionFor(entry.name))) {
      yield path;
    }
  }
}

async function readPrefix(file) {
  const handle = await open(file, "r");
  try {
    const buffer = Buffer.alloc(pointerPrefix.length);
    const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
    return buffer.subarray(0, bytesRead).toString("utf8");
  } finally {
    await handle.close();
  }
}

const failed = [];
let checked = 0;

for await (const file of walk(docsRoot)) {
  checked += 1;
  const prefix = await readPrefix(file);
  if (prefix.startsWith(pointerPrefix)) {
    failed.push(file);
  }
}

if (failed.length > 0) {
  console.error("validate-lfs-assets: Git LFS pointer files found in docs assets:");
  for (const file of failed) {
    console.error(`  ${file}`);
  }
  console.error("\nRun `git lfs pull` or use `actions/checkout` with `lfs: true`.");
  process.exit(1);
}

console.log(`validate-lfs-assets: ${checked} docs assets are resolved`);
