// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Determinism check for the SDK generator.
 *
 * The generated SDK tree is gitignored and produced on `pnpm install`. To make
 * sure regeneration is reproducible (same inputs → same output), this script
 * runs `gen:all` twice and asserts the resulting trees are byte-identical.
 *
 * Failures here usually mean the generator (orval template, post-process step,
 * or input spec) is producing nondeterministic output — e.g. timestamps,
 * unstable map ordering, or randomized identifiers.
 */

import { execSync } from 'child_process';
import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { __dirname } from './getDirname';

const REPO_WEB = path.resolve(__dirname, '..', '..', '..');
const SDK_DIR = path.join(REPO_WEB, 'packages', 'sdk');
const GENERATED = path.join(SDK_DIR, 'generated');
const HASH_SENTINEL = '.input-hash';

const run = (cmd: string) => {
  console.log(`$ ${cmd}`);
  execSync(cmd, { stdio: 'inherit', cwd: REPO_WEB });
};

/**
 * Hash every file in the generated tree (path + contents), excluding the
 * input-hash sentinel which records the cache key rather than generator output.
 */
const hashGeneratedTree = (): string => {
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(fullPath);
      } else if (entry.isFile()) {
        files.push(fullPath);
      }
    }
  };
  walk(GENERATED);
  files.sort();

  const hash = crypto.createHash('sha256');
  for (const file of files) {
    const rel = path.relative(GENERATED, file);
    if (rel === HASH_SENTINEL) continue;
    hash.update(`${rel}\0`);
    hash.update(fs.readFileSync(file));
    hash.update('\0');
  }
  return hash.digest('hex');
};

const main = async () => {
  if (!fs.existsSync(GENERATED)) {
    console.error(`Generated dir missing at ${GENERATED}. Run \`pnpm install\` first.`);
    process.exit(1);
  }

  console.log('▶ Run 1: force-regenerating SDK...');
  run('pnpm --filter @nemo/sdk gen:all');
  const hash1 = hashGeneratedTree();
  console.log(`  hash1 = ${hash1}\n`);

  console.log('▶ Run 2: force-regenerating SDK again...');
  run('pnpm --filter @nemo/sdk gen:all');
  const hash2 = hashGeneratedTree();
  console.log(`  hash2 = ${hash2}\n`);

  if (hash1 !== hash2) {
    console.error('❌ SDK generation is non-deterministic — two runs produced different output.');
    console.error('   Check generator templates and post-process steps for unstable output.');
    process.exit(1);
  }

  console.log('✅ SDK generation is deterministic.');
};

main().catch((error) => {
  console.error('💥 Determinism check failed:', error);
  process.exit(1);
});
