// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Splits `items` into `columnCount` columns with sizes differing by at most one. */
export const splitIntoEqualColumns = <T>(
  items: readonly T[],
  columnCount: number
): T[][] => {
  if (columnCount <= 0 || items.length === 0) {
    return [];
  }

  const columns: T[][] = Array.from({ length: columnCount }, () => []);
  const baseSize = Math.floor(items.length / columnCount);
  const remainder = items.length % columnCount;
  let index = 0;

  for (let column = 0; column < columnCount; column += 1) {
    const size = baseSize + (column < remainder ? 1 : 0);
    columns[column] = items.slice(index, index + size);
    index += size;
  }

  return columns;
};
