// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

async function main() {
  try {
    const { stdout: beforeOutput } = await execAsync('git diff --name-status');
    const beforeFiles = new Set(beforeOutput.trim().split('\n').filter(Boolean));

    // Run pnpm gen
    console.log('Running pnpm gen...');
    try {
      await execAsync('pnpm gen');
    } catch (error) {
      console.error('Error generating files:', error);
      process.exit(1);
    }

    console.log('Checking for file diffs...');
    const { stdout: afterOutput } = await execAsync('git diff --name-status');
    const newlyChanged = afterOutput
      .trim()
      .split('\n')
      .filter((line) => line && !beforeFiles.has(line));

    if (newlyChanged.length > 0) {
      console.error(
        '❌ Generated files are out of sync. Run `make lint-fix` (or `cd web && pnpm gen`) and commit the changes.'
      );
      console.error('Changed files:');
      console.error(newlyChanged.join('\n'));
      process.exit(1);
    }

    console.log('✅ All generated files are up to date.');
  } catch (error) {
    console.error('Error:', error);

    process.exit(1);
  }
}

main();
