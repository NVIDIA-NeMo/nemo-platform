// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { spawn } from "node:child_process";
import { watch } from "node:fs";
import { utimes } from "node:fs/promises";
import { constants } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const fernDir = path.resolve(scriptDir, "..");
const docsRoot = path.resolve(fernDir, "..");
const reloadTrigger = path.join(fernDir, "docs.yml");
const reloadDebounceMs = 150;
const ignoredPrefix = "fern/";

let debounceTimer = null;
let shuttingDown = false;

function log(message) {
  process.stdout.write(`[docs-watch] ${message}\n`);
}

async function touchReloadTrigger(changedPath) {
  const now = new Date();
  await utimes(reloadTrigger, now, now);
  log(`triggered Fern reload via docs.yml after change in ${changedPath}`);
}

function clearPendingReload() {
  if (debounceTimer === null) {
    return;
  }
  clearTimeout(debounceTimer);
  debounceTimer = null;
}

function scheduleReload(relativePath) {
  clearPendingReload();

  debounceTimer = setTimeout(() => {
    debounceTimer = null;
    touchReloadTrigger(relativePath).catch((error) => {
      log(`failed to trigger reload: ${error.message}`);
    });
  }, reloadDebounceMs);
}

function shouldIgnore(relativePath) {
  const normalized = path.posix.normalize(relativePath.split(path.sep).join("/"));
  return normalized.startsWith(ignoredPrefix);
}

const fern = spawn("npx", ["-y", "fern-api@latest", "docs", "dev"], {
  cwd: fernDir,
  stdio: "inherit",
});

const watcher = watch(
  docsRoot,
  { recursive: true },
  (_eventType, filename) => {
    const relativePath = filename ? filename.toString() : "";
    if (shouldIgnore(relativePath)) {
      return;
    }
    scheduleReload(relativePath);
  },
);

watcher.on("error", (error) => {
  log(`watcher error: ${error.message}`);
});

function closeWatcher() {
  watcher.close();
}

function signalExitCode(signal) {
  const signalNumber = constants.signals[signal];
  return signalNumber ? 128 + signalNumber : 1;
}

function shutdown(signal) {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  closeWatcher();
  clearPendingReload();
  fern.kill(signal);
  process.exit(signalExitCode(signal));
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

fern.on("exit", (code, signal) => {
  closeWatcher();
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
