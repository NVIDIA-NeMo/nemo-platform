// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Example Studio plugins bundled for this PR.
 *
 * Loaded via `@nemo/studio-plugins-external` (see `nemo-studio-ui` vite config). Replace with an
 * org package + `NEMO_STUDIO_PLUGINS_ENTRY` at deploy time.
 */

import { intakeTraceDetailPlugin } from '@nemo/studio-plugins-example/intake-trace-detail';
import type { StudioPlugin } from '@studio/plugins/types';

export const studioPlugins: readonly StudioPlugin[] = [intakeTraceDetailPlugin];
