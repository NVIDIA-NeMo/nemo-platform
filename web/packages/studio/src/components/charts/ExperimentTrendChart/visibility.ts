// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Where a viewer's show/hide choice for an experiment's over-time chart is kept.
 *
 * Two components share this key — the detail route reads it, the edit modal clears it when the
 * experiment's `show_evaluations_over_time` flag changes — and a mismatch between them would fail
 * silently, leaving a stale choice outranking the new flag. So it is built in one place.
 *
 * An absent key is meaningful: it means "this viewer has never chosen", which is what lets the
 * flag decide. Store nothing to express that; do not store `false`.
 */
export const trendVisibilityStorageKey = (groupId: string | undefined): string =>
  `nemo-studio:experiment-trend:${groupId ?? ''}`;
