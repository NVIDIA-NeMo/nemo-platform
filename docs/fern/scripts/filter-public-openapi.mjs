#!/usr/bin/env node
/**
 * SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * Build the public Fern OpenAPI spec from the generated platform spec.
 *
 * The repo-root openapi/openapi.yaml remains the source of truth for SDK
 * generation and API validation. Public docs exclude services that are not part
 * of the shipped OSS docs surface yet.
 */

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const fernDir = resolve(scriptDir, "..");
const inputPath = resolve(fernDir, "openapi/openapi.yaml");
const outputPath = resolve(fernDir, "openapi/openapi.public.yaml");

const gatedPathPrefixes = ["/apis/intake/v2/"];
const httpMethods = new Set(["get", "put", "post", "delete", "options", "head", "patch", "trace"]);
const schemaRefPattern = /#\/components\/schemas\/([^'"\s\]}),]+)/g;

const source = await readFile(inputPath, "utf8");
const hadTrailingNewline = source.endsWith("\n");
const lines = source.split("\n");
if (hadTrailingNewline) {
  lines.pop();
}

function isPathKey(line) {
  return /^  \//.test(line) && /:\s*$/.test(line);
}

function isTopLevelKey(line) {
  return /^[A-Za-z][A-Za-z0-9_-]*:\s*$/.test(line);
}

function pathFromKey(line) {
  return line.trim().replace(/:\s*$/, "");
}

function isComponentSectionKey(line) {
  return /^  [A-Za-z][A-Za-z0-9_-]*:\s*$/.test(line);
}

function isSchemaKey(line) {
  return /^    [^\s].*:\s*$/.test(line);
}

function schemaNameFromKey(line) {
  return line.trim().replace(/:\s*$/, "");
}

function collectSchemaRefs(linesToScan) {
  const refs = new Set();
  const text = linesToScan.join("\n");
  for (const match of text.matchAll(schemaRefPattern)) {
    refs.add(match[1]);
  }
  return refs;
}

function splitSchemaBlocks(linesToSplit) {
  const parts = [];
  const schemas = new Map();
  let inSchemas = false;

  for (let i = 0; i < linesToSplit.length; ) {
    const line = linesToSplit[i];

    if (!inSchemas && line === "  schemas:") {
      inSchemas = true;
      parts.push({ type: "line", line });
      i += 1;
      continue;
    }

    if (inSchemas) {
      if (isSchemaKey(line)) {
        const name = schemaNameFromKey(line);
        const block = [line];
        i += 1;
        while (
          i < linesToSplit.length &&
          !isSchemaKey(linesToSplit[i]) &&
          !isTopLevelKey(linesToSplit[i]) &&
          !isComponentSectionKey(linesToSplit[i])
        ) {
          block.push(linesToSplit[i]);
          i += 1;
        }
        schemas.set(name, block);
        parts.push({ type: "schema", name });
        continue;
      }

      if (isTopLevelKey(line) || isComponentSectionKey(line)) {
        inSchemas = false;
      }
    }

    parts.push({ type: "line", line });
    i += 1;
  }

  return { parts, schemas };
}

function expandSchemaRefs(seedRefs, schemas) {
  const refs = new Set(seedRefs);
  let changed = true;

  while (changed) {
    changed = false;
    for (const schema of Array.from(refs)) {
      const block = schemas.get(schema);
      if (!block) {
        continue;
      }
      for (const ref of collectSchemaRefs(block)) {
        if (!refs.has(ref)) {
          refs.add(ref);
          changed = true;
        }
      }
    }
  }

  return refs;
}

const keptLines = [];
const removedLines = [];
let skippingPath = false;
let removedPaths = 0;
let removedOperations = 0;

for (const line of lines) {
  if (isPathKey(line)) {
    const path = pathFromKey(line);
    skippingPath = gatedPathPrefixes.some((prefix) => path.startsWith(prefix));
    if (skippingPath) {
      removedPaths += 1;
      removedLines.push(line);
      continue;
    }
  } else if (skippingPath && isTopLevelKey(line)) {
    skippingPath = false;
  }

  if (skippingPath) {
    const method = line.trim().replace(/:\s*$/, "");
    if (httpMethods.has(method)) {
      removedOperations += 1;
    }
    removedLines.push(line);
    continue;
  }

  keptLines.push(line);
}

const { parts, schemas } = splitSchemaBlocks(keptLines);
const baseLines = parts.flatMap((part) => (part.type === "line" ? [part.line] : []));
const reachableFromPublicSpec = expandSchemaRefs(collectSchemaRefs(baseLines), schemas);
const reachableFromRemovedPaths = expandSchemaRefs(collectSchemaRefs(removedLines), schemas);

let removedSchemas = 0;
const publicOutput = [];
for (const part of parts) {
  if (part.type === "line") {
    publicOutput.push(part.line);
    continue;
  }

  if (reachableFromRemovedPaths.has(part.name) && !reachableFromPublicSpec.has(part.name)) {
    removedSchemas += 1;
    continue;
  }

  publicOutput.push(...schemas.get(part.name));
}

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${publicOutput.join("\n")}${hadTrailingNewline ? "\n" : ""}`);

console.log(
  `filter-public-openapi: wrote openapi/openapi.public.yaml, removed ${removedOperations} operations across ${removedPaths} gated paths and ${removedSchemas} intake-only schemas`
);
