// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatEvaluatorScore } from '@nemo/common/src/utils/formatters';
import { useListEvaluations } from '@nemo/sdk/generated/platform/api';
import type { ExperimentResponse } from '@nemo/sdk/generated/platform/schema';
import { Card, Tag, Text } from '@nvidia/foundations-react-core';
import { MetricTrendPanel } from '@studio/components/charts/MetricTrendPanel';
import {
  DELTA_COMPARISON_LABEL,
  formatTrendDelta,
  toTrendSeries,
  TREND_EVALUATION_LIMIT,
} from '@studio/routes/ExperimentRoute/experimentTrend';
import { Metric } from '@studio/routes/ExperimentRoute/Metric';
import { UpdatedAt } from '@studio/routes/ExperimentRoute/UpdatedAt';
import { getExperimentDetailRoute } from '@studio/routes/utils';
import { type FC, useMemo } from 'react';
import { useNavigate } from 'react-router';

interface ExperimentCardProps {
  group: ExperimentResponse;
  workspace: string;
}

export const ExperimentCard: FC<ExperimentCardProps> = ({ group, workspace }) => {
  const navigate = useNavigate();
  const showTrend = Boolean(group.show_evaluations_over_time);

  // Only experiments flagged to graph over time pay for this; the rest render the plain card.
  const { data: evaluationsPage, isPending } = useListEvaluations(
    workspace,
    { filter: { experiment_id: group.id }, page_size: TREND_EVALUATION_LIMIT },
    { query: { enabled: showTrend && !!group.id } }
  );

  const series = useMemo(() => toTrendSeries(evaluationsPage?.data ?? []), [evaluationsPage]);

  // A flagged experiment with nothing to plot yet falls back to the plain card rather than
  // rendering an empty chart. Kept while the query is in flight so the card settles once,
  // into the skeleton, instead of flashing the count and then swapping to a chart.
  const renderTrend = showTrend && (isPending || series.length > 0);

  return (
    <Card
      interactive
      attributes={{ CardContent: { className: 'flex flex-row items-center gap-6 p-6' } }}
      onClick={() => navigate(getExperimentDetailRoute(workspace, group.name))}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          navigate(getExperimentDetailRoute(workspace, group.name));
        } else if (e.key === ' ') {
          e.preventDefault();
          navigate(getExperimentDetailRoute(workspace, group.name));
        }
      }}
    >
      {/* Main info */}
      <div className="flex flex-col items-start gap-2 flex-1">
        <div className="flex items-center gap-2">
          <Text kind="title/sm">{group.name}</Text>
          {group.is_favorite && (
            <Tag kind="outline" color="green" density="compact" readOnly>
              Favorite
            </Tag>
          )}
        </div>
        {group.description && (
          <Text kind="body/regular/sm" className="text-secondary">
            {group.description}
          </Text>
        )}
        <div className="flex items-center gap-4">
          {group.updated_at && <UpdatedAt datetime={group.updated_at} />}
        </div>
      </div>

      {/* Stats, or the trendline for experiments flagged to graph over time. */}
      {renderTrend ? (
        // The evaluator pills are buttons inside an interactive card; without this, selecting a
        // series would bubble up and navigate to the experiment instead of switching the chart.
        <div
          role="presentation"
          className="w-1/2 shrink-0"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          <MetricTrendPanel
            chartOnly
            title={group.name}
            series={series}
            isPending={isPending}
            chartHeight={48}
            comparisonLabel={DELTA_COMPARISON_LABEL}
            formatValue={formatEvaluatorScore}
            formatDelta={formatTrendDelta}
          />
        </div>
      ) : (
        <div className="flex shrink-0 items-center gap-6">
          <Metric title="Evaluations" value={String(group.evaluation_count ?? 0)} />
        </div>
      )}
    </Card>
  );
};
