// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from 'react';

export interface HighlightMetricDetail {
  readonly id: string;
  readonly label: string;
  readonly value: ReactNode;
}

export interface HighlightMetric {
  readonly id: string;
  readonly label: string;
  readonly value: ReactNode;
  /** Breakdown shown in a hover popover (e.g. input/output/cached for Total Tokens). */
  readonly details?: readonly HighlightMetricDetail[];
}

export interface KeyValueEntry {
  readonly id: string;
  readonly label: string;
  readonly value: ReactNode;
  readonly wrapValue?: boolean;
}
