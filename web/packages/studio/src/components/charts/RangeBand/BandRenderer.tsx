// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useId } from 'react';

interface AxisInstance {
  scale: ((v: number) => number) & { range?: () => number[] };
}

export interface BandRendererProps {
  xKey?: string;
  lowerKey?: string;
  upperKey?: string;
  fill?: string;
  fillOpacity?: number;
  xAxisMap?: Record<string, AxisInstance>;
  yAxisMap?: Record<string, AxisInstance>;
  data?: Record<string, unknown>[];
  [key: string]: unknown;
}

export function BandRenderer({
  xAxisMap,
  yAxisMap,
  data = [],
  xKey = 'step',
  lowerKey = 'lower',
  upperKey = 'upper',
  fill = '#3d8a1e',
  fillOpacity = 0.5,
}: BandRendererProps) {
  const clipId = useId();
  const xAxis = xAxisMap ? Object.values(xAxisMap)[0] : null;
  const yAxis = yAxisMap ? Object.values(yAxisMap)[0] : null;
  if (!xAxis?.scale || !yAxis?.scale) return null;

  const pts = data.filter((d) => d[lowerKey] !== undefined && d[upperKey] !== undefined);
  if (pts.length < 2) return null;

  const upper = pts.map(
    (d) =>
      `${xAxis.scale(d[xKey] as number).toFixed(2)},${yAxis.scale(d[upperKey] as number).toFixed(2)}`
  );
  const lower = [...pts]
    .reverse()
    .map(
      (d) =>
        `${xAxis.scale(d[xKey] as number).toFixed(2)},${yAxis.scale(d[lowerKey] as number).toFixed(2)}`
    );

  const xRange = xAxis.scale.range?.();
  const yRange = yAxis.scale.range?.();
  const clipRect =
    xRange && yRange
      ? {
          x: Math.min(...xRange),
          y: Math.min(...yRange),
          width: Math.abs(xRange[1] - xRange[0]),
          height: Math.abs(yRange[1] - yRange[0]),
        }
      : null;

  return (
    <>
      {clipRect && (
        <defs>
          <clipPath id={clipId} data-testid="range-band-clip">
            <rect x={clipRect.x} y={clipRect.y} width={clipRect.width} height={clipRect.height} />
          </clipPath>
        </defs>
      )}
      <path
        data-testid="range-band-path"
        d={`M ${upper.join(' L ')} L ${lower.join(' L ')} Z`}
        fill={fill}
        fillOpacity={fillOpacity}
        stroke="none"
        clipPath={clipRect ? `url(#${clipId})` : undefined}
      />
    </>
  );
}
