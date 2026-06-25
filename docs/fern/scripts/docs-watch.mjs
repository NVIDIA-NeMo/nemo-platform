// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { spawn, spawnSync } from "node:child_process";
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
const openapiInputPrefix = "fern/openapi/";
const publicOpenapiPath = "fern/openapi/openapi.public.yaml";
const filterOpenapiScriptPath = "fern/scripts/filter-public-openapi.mjs";

let debounceTimer = null;
let pendingReloadRequiresOpenapi = false;
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

function scheduleReload(relativePath, requiresOpenapiPrepare = false) {
  clearPendingReload();
  pendingReloadRequiresOpenapi = pendingReloadRequiresOpenapi || requiresOpenapiPrepare;

  debounceTimer = setTimeout(() => {
    debounceTimer = null;
    const shouldRunOpenapiPrepare = pendingReloadRequiresOpenapi;
    pendingReloadRequiresOpenapi = false;
    Promise.resolve()
      .then(() => {
        if (shouldRunOpenapiPrepare) {
          prepareOpenapi();
        }
      })
      .then(() => touchReloadTrigger(relativePath))
      .catch((error) => {
        log(`failed to trigger reload: ${error.message}`);
      });
  }, reloadDebounceMs);
}

function normalizeWatchedPath(relativePath) {
  return path.posix.normalize(relativePath.split(path.sep).join("/"));
}

function shouldPrepareOpenapi(normalizedPath) {
  return (
    normalizedPath === filterOpenapiScriptPath ||
    (normalizedPath.startsWith(openapiInputPrefix) && normalizedPath !== publicOpenapiPath)
  );
}

function shouldIgnore(normalizedPath) {
  return normalizedPath.startsWith(ignoredPrefix) && !shouldPrepareOpenapi(normalizedPath);
}

function prepareOpenapi() {
  const result = spawnSync("node", ["scripts/filter-public-openapi.mjs"], {
    cwd: fernDir,
    stdio: "inherit",
  });

  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function spawnFernDev() {
  prepareOpenapi();
  return spawn("npx", ["-y", "fern-api@latest", "docs", "dev"], {
    cwd: fernDir,
    stdio: "inherit",
  });
}

const fern = spawnFernDev();

const watcher = watch(
  docsRoot,
  { recursive: true },
  (_eventType, filename) => {
    const relativePath = filename ? filename.toString() : "";
    const normalizedPath = normalizeWatchedPath(relativePath);
    if (shouldIgnore(normalizedPath)) {
      return;
    }
    scheduleReload(relativePath, shouldPrepareOpenapi(normalizedPath));
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
