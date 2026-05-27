// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * This script generates the types for the openapi specs.
 *
 * For private GitHub raw URLs, set the GITHUB_TOKEN environment variable.
 * For local files, no token is required.
 */
import { execSync } from 'child_process';
import fs from 'fs';
import os from 'os';
import { serviceConfigs } from './constants';
import path from 'path';
import { generateCustomFetcher } from './generateCustomFetcher';
import { getGithubTokenHeaders } from './githubTokenHeaders';

const githubToken = process.env.GITHUB_TOKEN;
const client = process.env.ORVAL_CLIENT;

const service = process.argv[2] as keyof typeof serviceConfigs;
const config = serviceConfigs[service];

if (!config) {
  throw new Error('Unsupported OpenAPI Spec.');
}

const getFile = async () => {
  if (config.url.startsWith('http')) {
    const remoteUrl = new URL(config.url);
    const headers = getGithubTokenHeaders(remoteUrl, githubToken);
    const res = await fetch(config.url, headers ? { headers } : undefined);
    if (Math.floor(res.status / 100) !== 2) {
      throw new Error(`${res.status} - Failed to fetch spec. ${res.statusText}`);
    }
    return await res.text();
  } else {
    // Load local file otherwise
    const filePath = path.resolve(__dirname, config.url);
    const spec = fs.readFileSync(filePath, 'utf8');
    return spec;
  }
};

/**
 * Post-process generated Zod files to fix type errors.
 * Adds proper type assertions to array constants that are used as default values in Zod schemas.
 */
const postProcessZodFiles = (zodPath: string) => {
  const zodDefaultFile = path.join(__dirname, '..', zodPath);

  if (!fs.existsSync(zodDefaultFile)) {
    console.log(`Zod file not found at ${zodDefaultFile}, skipping post-processing`);
    return;
  }

  console.log(`Post-processing Zod file: ${zodDefaultFile}`);

  const content = fs.readFileSync(zodDefaultFile, 'utf8');
  const lines = content.split('\n');
  let fixCount = 0;

  // Fix both patterns of SupportedJobTypesDefault constants:
  // Pattern 1 (multi-line):
  //   export const ...SupportedJobTypesDefault = [
  //     `retriever`,
  //   ];
  // Pattern 2 (single-line):
  //   export const ...SupportedJobTypesDefault =
  //     [`retriever`];

  for (let i = 0; i < lines.length; i++) {
    // Pattern 1: Multi-line format
    if (lines[i].match(/^export const \w+SupportedJobTypesDefault = \[$/)) {
      if (i + 2 < lines.length) {
        const literalMatch = lines[i + 1].match(/^\s*`(\w+)`,$/);
        const closingMatch = lines[i + 2].match(/^\];$/);

        if (literalMatch && closingMatch && !lines[i + 2].includes(' as ')) {
          const literalValue = literalMatch[1];
          lines[i + 2] = `] as ["${literalValue}"];`;
          fixCount++;
        }
      }
    }

    // Pattern 2: Single-line format
    if (lines[i].match(/SupportedJobTypesDefault =$/)) {
      if (i + 1 < lines.length) {
        const nextLineMatch = lines[i + 1].match(/^\s+\[`(\w+)`\];$/);

        if (nextLineMatch && !lines[i + 1].includes(' as ')) {
          const literalValue = nextLineMatch[1];
          lines[i + 1] = `  [\`${literalValue}\`] as ["${literalValue}"];`;
          fixCount++;
        }
      }
    }
  }

  if (fixCount > 0) {
    fs.writeFileSync(zodDefaultFile, lines.join('\n'), 'utf8');
    console.log(`✓ Fixed ${fixCount} SupportedJobTypesDefault constants`);
  } else {
    console.log('✓ No fixes needed');
  }
};

const main = async () => {
  console.log(`Generating types for: ${service}.`);
  const spec = await getFile();
  // Per-run temp dir with random suffix avoids predictable paths in a shared tmp.
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'openapi-spec-'));
  const tempFile = path.join(tempDir, `${config.path}.yaml`);
  const clientVar = client ? `ORVAL_CLIENT=${client}` : '';
  const target =
    client === 'zod'
      ? `./generated/${config.path}/zod/index.ts`
      : `./generated/${config.path}/api.ts`;
  fs.writeFileSync(tempFile, spec);

  if (client !== 'zod') {
    console.log(`Generating custom fetcher for: ${config.path}.`);
    generateCustomFetcher(config);
  }

  try {
    execSync(
      `ORVAL_SERVICE=${service} ORVAL_INPUT=${tempFile} ${clientVar} ORVAL_TARGET=${target} ORVAL_SCHEMAS=./generated/${config.path}/schema pnpm exec orval`,
      {
        stdio: 'inherit',
      }
    );

    // Post-process Zod files if generating with zod client
    if (client === 'zod') {
      postProcessZodFiles(`./generated/${config.path}/zod/default.ts`);
    }
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
};

main();
