// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { StudioPlugin } from '@studio/plugins/types';

/** Fallback when `manifest.local.ts` is absent (CI and fresh clones). */
export const LOCAL_STUDIO_PLUGINS: readonly StudioPlugin[] = [];
