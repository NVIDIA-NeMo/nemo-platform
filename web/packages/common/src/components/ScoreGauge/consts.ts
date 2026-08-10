// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

export const SCORE_TIER_COLORS = {
  Excellent: '#22c55e',
  'Very Good': '#84cc16',
  Good: '#eab308',
  Moderate: '#f97316',
  Poor: '#ef4444',
} as const;

export type ScoreTier = keyof typeof SCORE_TIER_COLORS | 'Unavailable';

export const UNAVAILABLE_COLOR = '#888888';

export const GRADIENT_PALETTE: [number, number, number][] = [
  [239, 68, 68],
  [249, 115, 22],
  [234, 179, 8],
  [132, 204, 22],
  [34, 197, 94],
];

export const CENTER = 50;
export const RADIUS = 38;
export const ARC_START = 135;
export const ARC_SWEEP = 270;

export const GRADIENT_SEGMENTS = 120;
