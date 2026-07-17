// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack, Text } from '@nvidia/foundations-react-core';
import { Empty } from '@studio/components/Empty';
import type { CustomizationMetricValue } from '@studio/types/customization';
import { type ComponentProps, useMemo } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  TooltipProps,
  XAxis,
  YAxis,
} from 'recharts';

interface Props {
  trainLoss?: CustomizationMetricValue[];
  valLoss?: CustomizationMetricValue[];
  height?: number;
  attributes?: {
    XAxis?: ComponentProps<typeof XAxis>;
  };
}

interface ChartDataPoint {
  step: number;
  epoch?: number;
  trainLoss?: number;
  valLoss?: number;
  trainLossInterpolated?: boolean;
  valLossInterpolated?: boolean;
}

// Linear interpolation helper
const interpolateValue = (step: number, data: CustomizationMetricValue[]): number | undefined => {
  if (data.length === 0) return undefined;

  // Find the two closest points
  let before: CustomizationMetricValue | undefined;
  let after: CustomizationMetricValue | undefined;

  for (const point of data) {
    if (point.step === undefined) continue;

    if (point.step === step) {
      // Exact match, no interpolation needed
      return point.value;
    }

    if (point.step < step) {
      if (!before || before.step === undefined || point.step > before.step) {
        before = point;
      }
    } else if (point.step > step) {
      if (!after || after.step === undefined || point.step < after.step) {
        after = point;
      }
    }
  }

  // If we have both before and after points, interpolate
  if (
    before?.step !== undefined &&
    after?.step !== undefined &&
    before.value !== undefined &&
    after.value !== undefined
  ) {
    const stepDiff = after.step - before.step;
    const valueDiff = after.value - before.value;
    const stepRatio = (step - before.step) / stepDiff;
    return before.value + valueDiff * stepRatio;
  }

  return undefined;
};

export function TrainValidationLossLineChart({
  trainLoss = [],
  valLoss = [],
  height = 400,
  attributes = {},
}: Props) {
  const { XAxis: xAxisAttributes } = attributes;
  const chartData = useMemo((): ChartDataPoint[] => {
    // Create a map of all steps with their data
    const dataMap = new Map<number, ChartDataPoint>();

    trainLoss.forEach((point) => {
      if (point.step !== undefined) {
        dataMap.set(point.step, {
          step: point.step,
          epoch: point.epoch,
          trainLoss: point.value,
          trainLossInterpolated: false,
        });
      }
    });

    valLoss.forEach((point) => {
      if (point.step !== undefined) {
        const existing = dataMap.get(point.step);
        if (existing) {
          existing.valLoss = point.value;
          existing.valLossInterpolated = false;
          existing.epoch = existing.epoch ?? point.epoch;
        } else {
          dataMap.set(point.step, {
            step: point.step,
            epoch: point.epoch,
            valLoss: point.value,
            valLossInterpolated: false,
          });
        }
      }
    });

    // Convert map to sorted array
    const sortedData = Array.from(dataMap.values()).sort((a, b) => a.step - b.step);

    // Interpolate missing values
    sortedData.forEach((point) => {
      if (point.trainLoss === undefined && trainLoss.length > 0) {
        const interpolated = interpolateValue(point.step, trainLoss);
        if (interpolated !== undefined) {
          point.trainLoss = interpolated;
          point.trainLossInterpolated = true;
        }
      }

      if (point.valLoss === undefined && valLoss.length > 0) {
        const interpolated = interpolateValue(point.step, valLoss);
        if (interpolated !== undefined) {
          point.valLoss = interpolated;
          point.valLossInterpolated = true;
        }
      }
    });

    return sortedData;
  }, [trainLoss, valLoss]);

  const hasTrainData = useMemo(() => chartData.some((d) => d.trainLoss !== undefined), [chartData]);
  const hasValData = useMemo(() => chartData.some((d) => d.valLoss !== undefined), [chartData]);

  // Steps at which a new epoch begins (skipping the first epoch's start), used to draw boundaries.
  const epochBoundaries = useMemo(() => {
    const boundaries: { step: number; epoch: number }[] = [];
    let previousEpoch: number | undefined;
    for (const point of chartData) {
      if (point.epoch !== undefined && point.epoch !== previousEpoch) {
        if (previousEpoch !== undefined) {
          boundaries.push({ step: point.step, epoch: point.epoch });
        }
        previousEpoch = point.epoch;
      }
    }
    return boundaries;
  }, [chartData]);

  if (chartData.length === 0) {
    return <Empty title="No training data available" />;
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData}>
        <CartesianGrid
          strokeDasharray="3 3"
          stroke="var(--border-color-base)"
          strokeOpacity={0.5}
        />
        <XAxis
          dataKey="step"
          label={{ value: 'Steps', position: 'insideBottom', offset: -5 }}
          type="number"
          domain={['dataMin', 'dataMax']}
          {...xAxisAttributes}
        />
        <YAxis label={{ value: 'Data Loss', angle: -90, position: 'insideLeft' }} />
        <Tooltip
          content={<CustomTooltip />}
          cursor={{ stroke: 'var(--border-color-accent-gray)', strokeWidth: 1 }}
        />
        <Legend
          iconType="square"
          wrapperStyle={{
            paddingTop: '24px',
          }}
          formatter={(value) => (
            <Text kind="label/regular/md" className="ml-1 text-placeholder">
              {value}
            </Text>
          )}
        />
        {epochBoundaries.map((boundary) => (
          <ReferenceLine
            key={`epoch-${boundary.epoch}`}
            x={boundary.step}
            stroke="var(--border-color-base)"
            strokeDasharray="4 4"
            label={{
              value: `Epoch ${boundary.epoch}`,
              position: 'insideTopRight',
              fontSize: 11,
              fill: 'var(--text-color-placeholder)',
            }}
          />
        ))}
        {hasTrainData && (
          <Line
            type="monotone"
            dataKey="trainLoss"
            stroke="var(--border-color-accent-blue)"
            name="Training Loss"
            dot={trainLoss.length <= 3}
            connectNulls
            strokeWidth={2}
          />
        )}
        {hasValData && (
          <Line
            type="monotone"
            dataKey="valLoss"
            stroke="var(--border-color-accent-yellow)"
            name="Validation Loss"
            dot={valLoss.length <= 3}
            connectNulls
            strokeWidth={2}
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  );
}

function CustomTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || !payload.length) {
    return null;
  }
  const dataPoint = payload[0]?.payload;

  return (
    <Stack
      gap="2"
      className="bg-component-tooltip border border-component-tooltip shadow-sm rounded-lg p-3"
    >
      <Text kind="label/semibold/md">
        Step {label}
        {dataPoint?.epoch !== undefined ? ` • Epoch ${dataPoint.epoch}` : ''}
      </Text>
      <Stack gap="1">
        <Text kind="body/regular/sm" className="text-accent-blue">
          Training Loss:{' '}
          {dataPoint?.trainLoss !== undefined
            ? `${dataPoint.trainLoss.toFixed(6)}${dataPoint.trainLossInterpolated ? ' (estimated)' : ''}`
            : '—'}
        </Text>
        <Text kind="body/regular/sm" className="text-accent-yellow">
          Validation Loss:{' '}
          {dataPoint?.valLoss !== undefined
            ? `${dataPoint.valLoss.toFixed(6)}${dataPoint.valLossInterpolated ? ' (estimated)' : ''}`
            : '—'}
        </Text>
      </Stack>
    </Stack>
  );
}
