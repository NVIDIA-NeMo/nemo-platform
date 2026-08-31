// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Trailing `-<n>` an earlier suggestion may have appended, so re-running the second run
 *  suggests `-3` rather than `-2-2`. */
const TRAILING_INDEX = /-(\d+)$/;

/**
 * A starting name for a run derived from `sourceName`: the source's own name with the next free
 * `-<n>` appended.
 *
 * The point is that the field arrives filled with something the user edits rather than writes.
 * Re-running `nemotron-super-3-temp-point5` to try a new temperature starts at
 * `nemotron-super-3-temp-point5-2`, and renaming that to `nemotron-super-3-temp-1` is a short edit
 * of an almost-right name. A generated random suffix would have to be cleared first, and reusing
 * the source's name verbatim would just conflict.
 */
export const suggestRunName = (sourceName: string, taken: Iterable<string>): string => {
  const stem = sourceName.replace(TRAILING_INDEX, '');
  const takenNames = new Set(taken);
  for (let index = 2; index < 1000; index += 1) {
    const candidate = `${stem}-${index}`;
    if (!takenNames.has(candidate)) return candidate;
  }
  return `${stem}-${Date.now()}`;
};
