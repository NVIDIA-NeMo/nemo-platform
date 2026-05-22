// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

async function main() {
  try {
    // Run pnpm gen
    console.log('Running pnpm gen...');
    try {
      await execAsync('pnpm gen');
    } catch (error) {
      console.error('Error generating files:', error);
      process.exit(1);
    }

    // Check for git diff
    console.log('Checking for file diffs...');
    const { stdout: diffOutput } = await execAsync('git diff --name-status');

    if (diffOutput.trim()) {
      console.error(
        '❌ Generated files are out of sync. Run `make lint-fix` (or `cd web && pnpm gen`) and commit the changes.'
      );
      console.error('Changed files:');
      console.error(diffOutput);
      process.exit(1);
    }

    console.log('✅ All generated files are up to date.');
  } catch (error) {
    console.error('Error:', error);

    process.exit(1);
  }
}

main();
