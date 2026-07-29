// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FC, ReactNode } from 'react';

export interface ComparisonRunCellProps {
  readonly children: ReactNode;
}

/** Wraps both the header and the body cell of a run column so the two share one box model and
 * line up. `data-fixed-width` keeps the column from stretching under the pinned-column flex
 * rules in StudioDataView.css. */
export const ComparisonRunCell: FC<ComparisonRunCellProps> = ({ children }) => (
  <div data-fixed-width className="flex h-full items-center text-left">
    {children}
  </div>
);
