// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Single predicate for the managed/external agent branch, so callers don't
 * repeat the `source === 'external'` string comparison. Accepts anything with a
 * `source` field (the SDK `Agent` or a table row).
 */
export const isExternalAgent = (agent?: { source?: string | null }): boolean =>
  agent?.source === 'external';
