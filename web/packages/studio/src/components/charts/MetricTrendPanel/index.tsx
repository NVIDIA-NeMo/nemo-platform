// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Button,
  Flex,
  PanelContent,
  PanelHeader,
  PanelRoot,
  Stack,
  Tag,
  Text,
} from '@nvidia/foundations-react-core';
import { useNvColorMode } from '@studio/components/DagCanvas/useNvColorMode';
import { StackedSkeleton } from '@studio/components/StackedSkeleton';
import { Triangle } from 'lucide-react';
import { FC, useId, useMemo, useState } from 'react';
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export interface MetricTrendPoint {
  /** X-axis label for the point, shown in the tooltip. */
  label: string;
  value: number;
}

export interface MetricTrendSeries {
  id: string;
  /** Pill label, e.g. "Solved". */
  label: string;
  value: number;
  /** Change over the compared period. Positive renders up, negative down. */
  delta?: number;
  points: MetricTrendPoint[];
}

interface Props {
  title: string;
  description?: string;
  series: MetricTrendSeries[];
  /** Qualifies the delta, e.g. "vs. 7 days ago". */
  comparisonLabel?: string;
  /** Caption under the value, e.g. "Latest result". */
  valueLabel?: string;
  /** Controls the active pill. Leave undefined to let the panel manage it. */
  selectedSeriesId?: string;
  onSeriesChange?: (seriesId: string) => void;
  onViewClick?: () => void;
  viewLabel?: string;
  formatValue?: (value: number) => string;
  formatDelta?: (delta: number) => string;
  chartHeight?: number;
  isPending?: boolean;
  /**
   * Render only the value, pills, and chart, dropping the surrounding panel and its header.
   * Use when the embedding container already shows the title and description — `title` is
   * still required, as it names the pill group for screen readers.
   */
  chartOnly?: boolean;
}

const DEFAULT_CHART_HEIGHT = 160;

/**
 * The area fill sits on a near-black surface in dark mode, so the light-mode opacities
 * wash out to almost nothing. Carry more of the accent color, and keep a floor at the
 * bottom of the gradient so the fill stays readable all the way down.
 */
const AREA_GRADIENT = {
  dark: { top: 0.65, mid: 0.3, bottom: 0.08 },
  light: { top: 0.3, mid: 0.12, bottom: 0 },
} as const;

const formatPercent = (value: number): string => `${value.toFixed(1)}%`;

const formatSignedDelta = (delta: number): string =>
  `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${Math.abs(delta).toFixed(1)}`;

export const MetricTrendPanel: FC<Props> = ({
  title,
  description,
  series,
  comparisonLabel,
  valueLabel,
  selectedSeriesId,
  onSeriesChange,
  onViewClick,
  viewLabel = 'View',
  formatValue = formatPercent,
  formatDelta = formatSignedDelta,
  chartHeight = DEFAULT_CHART_HEIGHT,
  isPending = false,
  chartOnly = false,
}) => {
  // useId() emits colons, which are not valid inside an SVG `url(#...)` reference.
  const gradientId = `metric-trend-${useId().replace(/:/g, '')}`;
  const [internalSeriesId, setInternalSeriesId] = useState<string | undefined>(series[0]?.id);

  const activeId = selectedSeriesId ?? internalSeriesId;
  const active = useMemo(
    () => series.find((s) => s.id === activeId) ?? series[0],
    [series, activeId]
  );

  const selectSeries = (seriesId: string) => {
    if (selectedSeriesId === undefined) {
      setInternalSeriesId(seriesId);
    }
    onSeriesChange?.(seriesId);
  };

  const delta = active?.delta;
  const isNegative = delta !== undefined && delta < 0;
  const isZero = delta === 0;
  const deltaColor = isZero ? 'gray' : isNegative ? 'red' : 'green';
  const lineColor = isNegative ? 'var(--text-color-accent-red)' : 'var(--text-color-brand)';
  const colorMode = useNvColorMode();
  const gradient = colorMode === 'dark' ? AREA_GRADIENT.dark : AREA_GRADIENT.light;

  // The chart bleeds into the panel's right and bottom padding; the value column pads itself
  // back so it stays optically centered against the trendline. A `chartOnly` caller supplies
  // its own container, so there is no panel padding to bleed into.
  const trend = (
    <Flex
      align="center"
      gap="density-2xl"
      className={chartOnly ? undefined : '-mb-density-2xl -mr-density-2xl'}
    >
      <Stack gap="density-xs" className="shrink-0 pb-density-2xl">
        <Text kind="display/lg">{active ? formatValue(active.value) : '—'}</Text>

        {delta !== undefined && (
          <Flex align="center" gap="density-sm">
            <Tag readOnly color={deltaColor} density="compact">
              {!isZero && (
                <Triangle
                  size={12}
                  className={`fill-current ${isNegative ? 'rotate-180' : ''}`}
                  aria-hidden
                />
              )}
              {formatDelta(delta)}
            </Tag>
            {comparisonLabel && (
              <Text kind="body/regular/md" className="text-secondary">
                {comparisonLabel}
              </Text>
            )}
          </Flex>
        )}

        {valueLabel && (
          <Text kind="body/regular/md" className="text-secondary">
            {valueLabel}
          </Text>
        )}
      </Stack>

      <Stack gap="density-sm" className="min-w-0 flex-1">
        {series.length > 1 && (
          <Flex align="center" gap="density-sm" wrap="wrap" role="group" aria-label={title}>
            {series.map((s) => {
              const isActive = s.id === active?.id;
              return (
                <Tag
                  key={s.id}
                  color={isActive ? 'green' : 'gray'}
                  kind={isActive ? 'solid' : 'outline'}
                  selected={isActive}
                  aria-pressed={isActive}
                  onClick={() => selectSeries(s.id)}
                >
                  {s.label}
                </Tag>
              );
            })}
          </Flex>
        )}

        <div className="overflow-hidden rounded-br-density-xl">
          {isPending ? (
            <StackedSkeleton count={1} height={chartHeight} className="w-full" />
          ) : !active ? (
            // eslint-disable-next-line no-restricted-syntax -- chartHeight is a caller-controlled number, not a static Tailwind class
            <Flex align="center" justify="center" style={{ height: chartHeight }}>
              <Text kind="body/regular/md" className="text-secondary">
                No data available
              </Text>
            </Flex>
          ) : (
            <ResponsiveContainer width="100%" height={chartHeight}>
              <AreaChart data={active.points} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={lineColor} stopOpacity={gradient.top} />
                    <stop offset="55%" stopColor={lineColor} stopOpacity={gradient.mid} />
                    <stop offset="100%" stopColor={lineColor} stopOpacity={gradient.bottom} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="label" hide />
                <YAxis domain={['dataMin', 'dataMax']} hide />
                <Tooltip
                  cursor={{ stroke: 'var(--border-color-base)', strokeWidth: 1 }}
                  formatter={(value: number) => [formatValue(value), active.label]}
                  contentStyle={{
                    fontSize: 12,
                    backgroundColor: 'var(--background-color-component-tooltip)',
                    borderColor: 'var(--border-color-base)',
                    color: 'var(--text-color-base)',
                  }}
                  labelStyle={{ color: 'var(--text-color-base)' }}
                  itemStyle={{ color: 'var(--text-color-base)' }}
                />
                <Area
                  type="linear"
                  dataKey="value"
                  name={active.label}
                  stroke={lineColor}
                  strokeWidth={2}
                  fill={`url(#${gradientId})`}
                  dot={active.points.length <= 2}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      </Stack>
    </Flex>
  );

  if (chartOnly) return trend;

  return (
    <PanelRoot elevation="mid">
      <PanelHeader className="items-start">
        <Stack gap="density-xs" className="min-w-0 flex-1">
          <Text kind="label/bold/xl">{title}</Text>
          {description && (
            <Text kind="body/regular/md" className="text-secondary">
              {description}
            </Text>
          )}
        </Stack>
        {onViewClick && (
          <Button kind="tertiary" size="small" className="shrink-0" onClick={onViewClick}>
            {viewLabel}
          </Button>
        )}
      </PanelHeader>

      <PanelContent>{trend}</PanelContent>
    </PanelRoot>
  );
};
