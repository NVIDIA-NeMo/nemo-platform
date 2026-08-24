// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ChartCurve } from '@nemo/common/src/components/charts/types';
import { bandArea } from '@studio/components/charts/RangeBand/chartLayers';
import { DEFAULT_BAND_OPACITY } from '@studio/components/charts/RangeBand/consts';
import { useMemo, type ReactNode } from 'react';

export interface UseRangeBandOptions {
  name: string;
  lowerKey?: string;
  upperKey?: string;
  fill?: string;
  fillOpacity?: number;
  type?: ChartCurve;
  enabled?: boolean;
}

/**
 * Drops a single band into a chart you are already composing — reach for `<RangeBand />` when the
 * whole chart is the band. Returns one recharts `<Area>` to place among the chart's children.
 */
export function useRangeBand({
  name,
  lowerKey = 'lower',
  upperKey = 'upper',
  fill = 'var(--text-color-accent-green)',
  fillOpacity = DEFAULT_BAND_OPACITY,
  type = 'monotone',
  enabled = true,
}: UseRangeBandOptions): ReactNode {
  return useMemo(
    () =>
      enabled
        ? bandArea({ key: 'rb-band', name, lowerKey, upperKey, fill, fillOpacity, type })
        : null,
    [name, lowerKey, upperKey, fill, fillOpacity, type, enabled]
  );
}
