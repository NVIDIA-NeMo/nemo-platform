#!/usr/bin/env node
// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/* eslint-disable no-console -- CLI script */
/**
 * Fetches base-external.css + components.css from the Kaizen UI Foundations CDN
 * for the version of @nvidia/foundations-react-core pinned in pnpm-workspace.yaml,
 * and writes the combined output to src/generated/styles.css.
 */
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';

const PKG = '@nvidia/foundations-react-core';
const CDN = 'https://webassets.nvidia.com/kaizen-ui-foundations';
const CDN_URL = new URL(CDN);
const FILES = ['base-external.css', 'components.css'];

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const OUT_FILE = resolve(ROOT, 'src/generated/styles.css');
const WORKSPACE_CONFIG = resolve(ROOT, '../../pnpm-workspace.yaml');

const VERSION_TAG = '@version';

function log(message: string) {
  process.stdout.write(`${message}\n`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

async function readWorkspaceVersion() {
  const raw = await readFile(WORKSPACE_CONFIG, 'utf8');
  const workspace = parse(raw) as unknown;
  if (!isRecord(workspace)) {
    throw new Error(`Could not parse ${WORKSPACE_CONFIG}`);
  }

  const catalog = workspace.catalog;
  if (!isRecord(catalog)) {
    throw new Error(`Could not find catalog in ${WORKSPACE_CONFIG}`);
  }

  const version = catalog[PKG];
  if (typeof version !== 'string' || version.trim() === '') {
    throw new Error(`Could not read ${PKG} version from ${WORKSPACE_CONFIG}`);
  }

  const exactVersion = version.trim();
  if (!/^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(exactVersion)) {
    throw new Error(
      `Expected ${PKG} in ${WORKSPACE_CONFIG} to be an exact version, got "${version}"`
    );
  }

  return exactVersion;
}

async function readCachedVersion() {
  try {
    const existing = await readFile(OUT_FILE, 'utf8');
    const match = existing.match(new RegExp(`${VERSION_TAG}\\s+([^\\s*]+)`));
    return match?.[1] ?? null;
  } catch {
    return null;
  }
}

async function fetchCss(version: string, file: string) {
  const url = new URL(`${encodeURIComponent(version)}/${encodeURIComponent(file)}`, `${CDN}/`);
  if (url.protocol !== 'https:' || url.host !== CDN_URL.host) {
    throw new Error(`Refusing to fetch from disallowed origin: ${url.origin}`);
  }
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch ${url}: ${res.status} ${res.statusText}`);
  }
  return res.text();
}

function buildHeader(version: string) {
  return [
    '/* SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. */',
    '/* SPDX-License-Identifier: Apache-2.0 */',
    '/**',
    ' * GENERATED FILE — do not edit by hand.',
    ' *',
    ` * ${VERSION_TAG} ${version}`,
    ` * source: ${CDN}/${version}/{${FILES.join(',')}}`,
    ' */',
    '',
  ].join('\n');
}

async function main() {
  const version = await readWorkspaceVersion();
  const cached = await readCachedVersion();

  if (cached === version) {
    log(`[fetch-styles] cached styles already at ${version}, skipping`);
    return;
  }

  log(`[fetch-styles] fetching ${PKG}@${version} stylesheets…`);
  const parts = await Promise.all(
    FILES.map(async (file) => {
      const css = await fetchCss(version, file);
      return `/* --- ${file} --- */\n${css.trim()}\n`;
    })
  );

  await mkdir(dirname(OUT_FILE), { recursive: true });
  await writeFile(OUT_FILE, `${buildHeader(version)}${parts.join('\n')}`);
  log(`[fetch-styles] wrote ${OUT_FILE}`);
}

main().catch((err) => {
  console.error('[fetch-styles]', err);
  process.exit(1);
});
