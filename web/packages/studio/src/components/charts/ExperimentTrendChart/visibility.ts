// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Where a viewer's show/hide choice for an experiment's over-time chart is kept.
 *
 * Built in one place because more than one component reads it, and two components agreeing on a
 * string by convention would fail silently.
 */
export const trendVisibilityStorageKey = (groupId: string | undefined): string =>
  `nemo-studio:experiment-trend:${groupId ?? ''}`;

/**
 * A viewer's stored choice, stamped with the flag value it was made against.
 *
 * The flag is stored alongside the choice so the choice can expire on its own. Storing a bare
 * boolean does not work: the chart's default comes from the experiment's
 * `show_evaluations_over_time`, so a stale choice silently outranks a flag that has since changed,
 * and the owner who flips the flag sees nothing happen.
 */
export interface TrendVisibilityChoice {
  readonly visible: boolean;
  /** The `show_evaluations_over_time` value in force when the viewer chose. */
  readonly flag: boolean;
}

const isChoice = (value: unknown): value is TrendVisibilityChoice =>
  typeof value === 'object' &&
  value !== null &&
  typeof (value as TrendVisibilityChoice).visible === 'boolean' &&
  typeof (value as TrendVisibilityChoice).flag === 'boolean';

/**
 * Whether to show the chart: the viewer's choice while the flag still reads as it did when they
 * made it, and the flag itself once it has changed.
 *
 * Keying on the flag value rather than on a change event means this holds however the flag moved —
 * the edit modal, the API, the CLI, another tab, another user — and not only for edits this app
 * happened to witness. A value in the older bare-boolean format fails {@link isChoice} and so is
 * ignored, which retires it on first read rather than stranding viewers on a stale choice.
 */
export const resolveTrendVisible = (stored: unknown, flag: boolean): boolean =>
  isChoice(stored) && stored.flag === flag ? stored.visible : flag;
