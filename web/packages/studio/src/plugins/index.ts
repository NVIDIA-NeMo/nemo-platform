// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { studioPlugins as externalStudioPlugins } from '@nemo/studio-plugins-external';
import { LOCAL_STUDIO_PLUGINS } from '@studio/plugins/manifest.local';
import { CORE_STUDIO_PLUGINS } from '@studio/plugins/manifest.core';
import { mergeStudioPlugins } from '@studio/plugins/mergeStudioPlugins';

/**
 * Deployed Studio plugins — merged from platform core, local dev manifest, and org package.
 *
 * - `manifest.core.ts` — optional platform-owned plugins (empty by default).
 * - `manifest.local.ts` — gitignored local dev manifest (see `manifest.local.ts.example`).
 * - `@nemo/studio-plugins-external` — org package via `NEMO_STUDIO_PLUGINS_ENTRY` at build time.
 *
 * Plugin implementations live in `@nemo/studio-plugins-example` (this PR) or an org package via
 * `NEMO_STUDIO_PLUGINS_ENTRY`. Optional gitignored additions: `plugins/local/` + `manifest.local.ts`.
 */
export const STUDIO_PLUGINS = mergeStudioPlugins(
  CORE_STUDIO_PLUGINS,
  LOCAL_STUDIO_PLUGINS,
  externalStudioPlugins
);
