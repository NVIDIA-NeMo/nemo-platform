// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FADED_SERIES_OPACITY } from '@nemo/common/src/components/charts/tokens';
import type { ChartCurve } from '@nemo/common/src/components/charts/types';
import { ComparisonAnnotationLabel } from '@nemo/common/src/components/ComparisonLineChart/ComparisonAnnotationLabel';
import { ANNOTATION_COLOR } from '@nemo/common/src/components/ComparisonLineChart/consts';
import type { ColoredSeries } from '@nemo/common/src/components/ComparisonLineChart/useComparisonChartModel';
import type { ResolvedAnnotation } from '@nemo/common/src/components/ComparisonLineChart/utils';
import type { ReactElement } from 'react';
import { Line, ReferenceLine } from 'recharts';

/**
 * Plain functions, not components: recharts inspects each chart child's element type, so a wrapper
 * would hide the `<Line>`/`<ReferenceLine>`.
 */

export const renderAnnotations = (annotations: ResolvedAnnotation[]): ReactElement[] =>
  annotations.map((annotation) => (
    <ReferenceLine
      key={`annotation-${annotation.x}-${annotation.label}`}
      segment={[
        { x: annotation.x, y: annotation.fromY },
        { x: annotation.x, y: annotation.toY },
      ]}
      stroke={annotation.color ?? ANNOTATION_COLOR}
      strokeDasharray="4 4"
      ifOverflow="extendDomain"
      label={
        <ComparisonAnnotationLabel
          label={annotation.label}
          description={annotation.description}
          color={annotation.color}
          pointsUp={annotation.pointsUp}
          labelSide={annotation.labelSide}
        />
      }
    />
  ));

interface SeriesLineOptions {
  curve: ChartCurve;
  /** Fades every other line so a single series can be read out of a crowded chart. */
  hoveredId: string | null;
  showMarks?: boolean;
}

export const renderSeriesLines = (
  series: ColoredSeries[],
  { curve, hoveredId, showMarks }: SeriesLineOptions
): ReactElement[] =>
  series.map((entry) => (
    <Line
      key={entry.id}
      type={curve}
      dataKey={entry.id}
      name={entry.label}
      stroke={entry.resolvedColor}
      strokeWidth={2}
      strokeDasharray={entry.dashed ? '6 4' : undefined}
      strokeOpacity={hoveredId && hoveredId !== entry.id ? FADED_SERIES_OPACITY : 1}
      dot={showMarks ?? entry.data.length <= 3}
      activeDot={{ r: 4 }}
      connectNulls={false}
      isAnimationActive={false}
    />
  ));
