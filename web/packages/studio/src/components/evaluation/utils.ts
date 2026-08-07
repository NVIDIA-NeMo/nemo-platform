// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Pure score formatting helpers shared between the evaluator panel and
 *  the per-item reasoning component so they render badges identically. */

export const formatScore = (score: number | null | undefined): string =>
  typeof score === 'number' && Number.isFinite(score) ? score.toFixed(3) : '–';

export const scoreColor = (
  score: number | null | undefined
): 'green' | 'yellow' | 'red' | 'gray' => {
  if (typeof score !== 'number' || !Number.isFinite(score)) return 'gray';
  if (score >= 0.8) return 'green';
  if (score >= 0.5) return 'yellow';
  return 'red';
};
