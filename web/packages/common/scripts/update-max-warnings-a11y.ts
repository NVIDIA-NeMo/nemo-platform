#!/usr/bin/env node
// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { execSync } from 'child_process';
import fs from 'fs';
import path from 'path';

const pkgPath = path.resolve(process.cwd(), 'package.json');
const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8')) as {
  scripts: Record<string, string>;
};

// Run ESLint with the a11y config and capture JSON output
let output: string;
try {
  output = execSync(
    'eslint . --config ../../eslint.config.a11y.js --no-config-lookup --no-inline-config --format json',
    { encoding: 'utf8' }
  );
} catch (e) {
  const stdout = (e as { stdout: string }).stdout;
  if (!stdout) {
    console.error('eslint failed to produce output');
    process.exit(1);
  }
  output = stdout;
}

const results: Array<{ warningCount: number }> = JSON.parse(output);
const warningCount: number = results.reduce((sum, file) => sum + file.warningCount, 0);

// Find current max-warnings in lint:a11y script
const a11yScript: string = pkg.scripts['lint:a11y'];
if (!a11yScript) {
  console.error('No lint:a11y script found in package.json');
  process.exit(1);
}

const maxWarningsRegex = /--max-warnings (\d+)/;
const maxWarningsMatch = a11yScript.match(maxWarningsRegex);
if (!maxWarningsMatch) {
  console.error('lint:a11y script is missing --max-warnings <number>');
  process.exit(1);
}
const currentMax: number = parseInt(maxWarningsMatch[1], 10);

if (warningCount !== currentMax) {
  pkg.scripts['lint:a11y'] = a11yScript.replace(maxWarningsRegex, `--max-warnings ${warningCount}`);
  fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n');
  // eslint-disable-next-line no-console
  console.log(`Updated lint:a11y max-warnings from ${currentMax} to ${warningCount}`);
} else {
  // eslint-disable-next-line no-console
  console.log(`No update needed. Current warnings: ${warningCount}, max-warnings: ${currentMax}`);
}
