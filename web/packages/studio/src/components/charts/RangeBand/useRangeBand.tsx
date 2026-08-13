// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BandRenderer } from '@studio/components/charts/RangeBand/BandRenderer';
import { useMemo, type ReactNode } from 'react';
import { Area, Customized } from 'recharts';

export interface UseRangeBandOptions {
  name: string;
  lowerKey?: string;
  upperKey?: string;
  xKey?: string;
  fill?: string;
  fillOpacity?: number;
  enabled?: boolean;
}

// TODO: recharts v3 supports custom JSX chart children natively (no Customized wrapper needed).
// Once we upgrade from v2, replace this hook with a plain <RangeBand /> component.
// See: https://github.com/recharts/recharts/issues/2788 and https://github.com/recharts/recharts/wiki/3.0-migration-guide
export function useRangeBand({
  name,
  lowerKey = 'lower',
  upperKey = 'upper',
  xKey = 'step',
  fill = '#3d8a1e',
  fillOpacity = 0.5,
  enabled = true,
}: UseRangeBandOptions): ReactNode {
  return useMemo(() => {
    if (!enabled) return null;
    return [
      <Area
        key="rb-legend"
        dataKey={upperKey}
        stroke="none"
        fill={fill}
        fillOpacity={0}
        strokeOpacity={0}
        legendType="square"
        name={name}
        isAnimationActive={false}
        activeDot={false}
      />,
      <Customized
        key="rb-renderer"
        component={BandRenderer}
        lowerKey={lowerKey}
        upperKey={upperKey}
        xKey={xKey}
        fill={fill}
        fillOpacity={fillOpacity}
      />,
    ];
  }, [name, lowerKey, upperKey, xKey, fill, fillOpacity, enabled]);
}
