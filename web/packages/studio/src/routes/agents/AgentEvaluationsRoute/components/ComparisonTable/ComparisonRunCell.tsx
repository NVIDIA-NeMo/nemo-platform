// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FC, ReactNode } from 'react';

/** Wraps both the header and the body cell of a run column so the two share one box model and
 * line up. Negative margins cancel the table cell's own padding so the divider reaches the full
 * cell edge, the way TableColumnHeader's own full-bleed controls do. `data-fixed-width` keeps the
 * column from stretching under the pinned-column flex rules in StudioDataView.css. */
export const ComparisonRunCell: FC<{ children: ReactNode }> = ({ children }) => (
  <div
    data-fixed-width
    className="-mx-(--table-cell-inline-padding) -my-(--table-cell-block-padding) flex h-full w-[calc(100%+var(--table-cell-inline-padding)*2)] items-center px-(--table-cell-inline-padding) py-(--table-cell-block-padding) text-left"
  >
    {children}
  </div>
);
