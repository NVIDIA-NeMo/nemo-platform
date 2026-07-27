// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { Text } from '@nvidia/foundations-react-core';
import { ComparisonColumnHeader } from '@studio/routes/agents/AgentEvaluationsRoute/components/ComparisonTable/ComparisonColumnHeader';
import { ComparisonDeltaCell } from '@studio/routes/agents/AgentEvaluationsRoute/components/ComparisonTable/ComparisonDeltaCell';
import { ComparisonPinnedCell } from '@studio/routes/agents/AgentEvaluationsRoute/components/ComparisonTable/ComparisonPinnedCell';
import { ComparisonRunCell } from '@studio/routes/agents/AgentEvaluationsRoute/components/ComparisonTable/ComparisonRunCell';
import {
  baselineForComparisons,
  candidatesForComparisons,
  deltaFromBaseline,
  metricNamesForComparisons,
  scoreForMetric,
  type ComparisonEntry,
} from '@studio/routes/agents/AgentEvaluationsRoute/components/ComparisonTable/types';
import { formatScore } from '@studio/routes/agents/AgentEvaluationsRoute/evalScores';
import { useMemo, type ComponentProps, type FC } from 'react';

const METRIC_COLUMN_ID = 'metric';
const BASELINE_COLUMN_ID = 'baseline';
const PINNED_COLUMNS = { left: [METRIC_COLUMN_ID, BASELINE_COLUMN_ID], right: [] };

/** Every column is the same width so runs read as a grid. Pinning switches rows to flex layout
 * (StudioDataView.css), where unpinned cells stretch unless a `data-fixed-width` descendant
 * opts them out — ComparisonDeltaCell and ComparisonColumnHeader carry that marker. */
const COLUMN_SIZE = 220;

/** Column widths reach the DOM as a `--col-<id>-size` custom property, so an id has to be a valid
 * CSS identifier. Run ids routinely contain characters that are not. */
const runColumnId = (evaluationId: string): string => `run-${evaluationId.replace(/[^\w-]/g, '-')}`;

interface MetricRow {
  metricName: string;
}

export interface ComparisonTableProps {
  /** Runs made with one persisted eval-config fileset. The first entry is the baseline every
   * other run is measured against; order the list to choose it. */
  evaluations: readonly ComparisonEntry[];
  /** Metrics where a lower score is the improvement (latency, cost, error rate). */
  lowerIsBetterMetrics?: readonly string[];
}

/** A matrix for comparing aggregate results from a single eval config. Metrics are rows and each
 * run is a column; the metric and baseline columns stay pinned so candidate runs can be scrolled
 * through side by side against the baseline. */
export const ComparisonTable: FC<ComparisonTableProps> = ({
  evaluations,
  lowerIsBetterMetrics,
}) => {
  const dataViewState = useStudioDataViewState({
    defaultPageSize: 25,
    columnPinning: PINNED_COLUMNS,
  });
  const baseline = useMemo(() => baselineForComparisons(evaluations), [evaluations]);
  const candidates = useMemo(() => candidatesForComparisons(evaluations), [evaluations]);
  const rows = useMemo<MetricRow[]>(
    () => metricNamesForComparisons(evaluations).map((metricName) => ({ metricName })),
    [evaluations]
  );
  const lowerIsBetter = useMemo(() => new Set(lowerIsBetterMetrics ?? []), [lowerIsBetterMetrics]);

  const makeColumns: ComponentProps<typeof StudioDataView<MetricRow>>['makeColumns'] = ({
    accessor,
  }) => [
    accessor((original) => original.metricName, {
      id: METRIC_COLUMN_ID,
      header: () => <ComparisonPinnedCell>Metric</ComparisonPinnedCell>,
      size: COLUMN_SIZE,
      enableSorting: false,
      cell: ({ row }) => (
        <ComparisonPinnedCell>
          <Text kind="body/semibold/md">{row.original.metricName}</Text>
        </ComparisonPinnedCell>
      ),
    }),
    accessor((original) => (baseline ? scoreForMetric(baseline, original.metricName) : null), {
      id: BASELINE_COLUMN_ID,
      header: () => (
        <ComparisonPinnedCell>
          {baseline ? <ComparisonColumnHeader evaluation={baseline} isBaseline /> : 'Baseline'}
        </ComparisonPinnedCell>
      ),
      size: COLUMN_SIZE,
      enableSorting: false,
      cell: ({ row }) => (
        <ComparisonPinnedCell>
          <Text className="tabular-nums" kind="body/regular/md">
            {formatScore(baseline ? scoreForMetric(baseline, row.original.metricName) : null)}
          </Text>
        </ComparisonPinnedCell>
      ),
    }),
    ...candidates.map((evaluation) =>
      accessor((original) => scoreForMetric(evaluation, original.metricName), {
        id: runColumnId(evaluation.id),
        header: () => (
          <ComparisonRunCell>
            <ComparisonColumnHeader evaluation={evaluation} />
          </ComparisonRunCell>
        ),
        size: COLUMN_SIZE,
        enableSorting: false,
        cell: ({ row }) => (
          <ComparisonRunCell>
            <ComparisonDeltaCell
              delta={deltaFromBaseline(evaluation, baseline, row.original.metricName)}
              higherIsBetter={!lowerIsBetter.has(row.original.metricName)}
            />
          </ComparisonRunCell>
        ),
      })
    ),
  ];

  return (
    <StudioDataView<MetricRow>
      dataViewState={dataViewState}
      makeColumns={makeColumns}
      maxTwoLines={false}
      attributes={{
        DataViewRoot: { data: rows, totalCount: rows.length },
        DataViewTableContent: {
          renderEmptyState: () => (
            <TableEmptyState
              header="No Evaluations"
              emptyMessage="Select evaluations to compare."
            />
          ),
        },
      }}
    />
  );
};
