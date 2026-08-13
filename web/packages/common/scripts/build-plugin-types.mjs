// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { build } from 'rolldown';
import { dts } from 'rolldown-plugin-dts';

// Committed, not gitignored: `web-plugin-types` in CI regenerates this and
// fails on a diff, so a change to the surface can't land without the artifact
// out-of-tree plugins type against moving with it.
const OUT_DIR = 'plugin-types';

const LICENSE_BANNER =
  '// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.\n' +
  '// SPDX-License-Identifier: Apache-2.0';

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
  // The generator owns the header. Emitting it here means the pre-commit
  // copyright hook is a no-op on the artifact, so it can't rewrite the file out
  // of byte-equality with a fresh generation and break the CI drift check.
  output: { dir: OUT_DIR, format: 'esm', banner: LICENSE_BANNER },
});

console.log(`Plugin surface types written to ${OUT_DIR}/plugin.d.ts`);
