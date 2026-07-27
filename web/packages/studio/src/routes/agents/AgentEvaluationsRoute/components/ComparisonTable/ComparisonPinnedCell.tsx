// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FC, ReactNode } from 'react';

/** Pinned columns are centered and zero-padded by the shared pinned-column CSS in
 * StudioDataView.css, which is tuned for icon-only prebuilt columns. Restore the left-aligned,
 * padded look for pinned text columns. */
export const ComparisonPinnedCell: FC<{ children: ReactNode }> = ({ children }) => (
  <div className="w-full px-density-2xl text-left">{children}</div>
);
