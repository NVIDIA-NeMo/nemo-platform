#!/usr/bin/env node
// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ESLint } from 'eslint';
import fs from 'fs';
import path from 'path';

async function main() {
  const pkgPath = path.resolve(process.cwd(), 'package.json');
  const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8')) as {
    scripts?: Record<string, string>;
  };

  const scripts = pkg.scripts;
  const a11yScript = scripts?.['lint:a11y'];
  if (!scripts || !a11yScript) {
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

  // a11y flat config only; inline directives ignored
  const eslint = new ESLint({
    overrideConfigFile: path.resolve(process.cwd(), '../../eslint.config.a11y.js'),
    allowInlineConfig: false,
  });
  const results = await eslint.lintFiles(['.']);
  const warningCount: number = results.reduce((sum, result) => sum + result.warningCount, 0);

  if (warningCount !== currentMax) {
    scripts['lint:a11y'] = a11yScript.replace(maxWarningsRegex, `--max-warnings ${warningCount}`);
    fs.writeFileSync(pkgPath, JSON.stringify(pkg, null, 2) + '\n');
    // eslint-disable-next-line no-console
    console.log(`Updated lint:a11y max-warnings from ${currentMax} to ${warningCount}`);
  } else {
    // eslint-disable-next-line no-console
    console.log(`No update needed. Current warnings: ${warningCount}, max-warnings: ${currentMax}`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
