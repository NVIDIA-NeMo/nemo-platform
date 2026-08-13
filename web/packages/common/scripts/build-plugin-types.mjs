// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { build } from 'rolldown';
import { dts } from 'rolldown-plugin-dts';

const OUT_DIR = 'dist/plugin-types';

// Out-of-tree plugin repos can't resolve @nemo/common's sources: the package is
// unpublished and its imports resolve against this workspace's node_modules. So
// roll the plugin surface up into one .d.ts they can vendor and point tsconfig
// `paths` at. @nemo/sdk stays external — bundling it pulls in ~650 generated
// schema modules for the two types LogViewer and the job-status constants use,
// which a consumer can stub in a dozen lines. @assistant-ui is external because
// @assistant-ui/store's shipped .d.ts re-exports a name it doesn't declare, so
// inlining it fails the bundle; consumers install the real package for types.
await build({
  input: 'src/plugin.ts',
  platform: 'browser',
  external: [/^@nemo\/sdk/, /^@assistant-ui\//],
  plugins: [dts({ emitDtsOnly: true, tsconfig: 'tsconfig.plugin-types.json' })],
  output: { dir: OUT_DIR, format: 'esm' },
});

console.log(`Plugin surface types written to ${OUT_DIR}/plugin.d.ts`);
