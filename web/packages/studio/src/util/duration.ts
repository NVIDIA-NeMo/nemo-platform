// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Rendered when a duration is null/undefined. Matches the EM DASH used elsewhere for empty values. */
const EMPTY_VALUE = '—';

const MS_PER_SECOND = 1000;
const MS_PER_MINUTE = 60 * MS_PER_SECOND;
const MS_PER_HOUR = 60 * MS_PER_MINUTE;

/**
 * Format a duration given in milliseconds as compact human-readable segments,
 * e.g. `10m 12s 13ms`, `12s 34ms`, or `34ms`.
 *
 * Segments run from the highest non-zero unit down to the lowest non-zero unit
 * (leading and trailing zero units are dropped, interior zeros are kept so
 * `1h 0m 5s` stays unambiguous). Sub-millisecond values keep two decimals of
 * precision (`0.34ms`) so span timings are not rounded away.
 */
export const formatDuration = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return EMPTY_VALUE;
  if (value <= 0) return '0ms';
  if (value < 1) return `${Number(value.toFixed(2))}ms`;

  const total = Math.round(value);
  const segments: string[] = [];
  const hours = Math.floor(total / MS_PER_HOUR);
  const minutes = Math.floor((total % MS_PER_HOUR) / MS_PER_MINUTE);
  const seconds = Math.floor((total % MS_PER_MINUTE) / MS_PER_SECOND);
  const millis = total % MS_PER_SECOND;

  const parts: [number, string][] = [
    [hours, 'h'],
    [minutes, 'm'],
    [seconds, 's'],
    [millis, 'ms'],
  ];

  // Drop leading zero units, keep everything from the first non-zero unit down
  // to the last non-zero unit (so interior zeros are preserved).
  let started = false;
  let lastNonZeroIndex = 0;
  parts.forEach(([amount], index) => {
    if (amount !== 0) lastNonZeroIndex = index;
  });
  parts.forEach(([amount, unit], index) => {
    if (amount !== 0) started = true;
    if (started && index <= lastNonZeroIndex) {
      segments.push(`${amount}${unit}`);
    }
  });

  return segments.join(' ');
};
