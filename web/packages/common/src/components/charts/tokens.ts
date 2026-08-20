// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Ordered so adjacent series stay distinguishable in both light and dark themes. */
export const SERIES_COLORS = [
  'var(--text-color-accent-blue)',
  'var(--text-color-accent-green)',
  'var(--text-color-accent-purple)',
  'var(--text-color-accent-yellow)',
  'var(--text-color-accent-teal)',
  'var(--text-color-accent-red)',
  'var(--text-color-accent-gray)',
] as const;

export const AXIS_COLOR = 'var(--border-color-base)';
export const AXIS_TEXT_COLOR = 'var(--text-color-placeholder)';
export const REFERENCE_LINE_COLOR = 'var(--border-color-accent-gray)';

export const DEFAULT_CHART_HEIGHT = 320;

/** How far non-hovered series fade so a single one can be read out of a crowded chart. */
export const FADED_SERIES_OPACITY = 0.15;
