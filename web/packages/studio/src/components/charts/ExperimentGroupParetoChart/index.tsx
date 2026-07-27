// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  getGetExperimentGroupQueryKey,
  useUpdateExperimentGroup,
} from '@nemo/sdk/generated/platform/api';
import type { ExperimentGroupResponse } from '@nemo/sdk/generated/platform/schema';
import {
  Button,
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import {
  buildParetoPoints,
  deriveParetoMetrics,
  metricLabel,
  type ParetoMetric,
  type ParetoPlotPoint,
} from '@studio/components/charts/ExperimentGroupParetoChart/paretoMetrics';
import { useParetoEvaluations } from '@studio/components/charts/ExperimentGroupParetoChart/useParetoEvaluations';
import type { EvaluationRow } from '@studio/components/dataViews/ExperimentGroupDataView/useExperimentGroupEvaluations';
import { useQueryClient } from '@tanstack/react-query';
import { Loader2, Save } from 'lucide-react';
import { type FC, useMemo, useState } from 'react';
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

interface ExperimentGroupParetoChartProps {
  workspace: string;
  group: ExperimentGroupResponse;
  /**
   * The group's full evaluation set, when the caller already has it loaded (a small group that fit on
   * the leaderboard's first page). Supplying it lets the chart render from the shared rows and skip its
   * own all-evaluations fetch — which re-runs the same server-side rollup.
   */
  preloadedEvaluations?: EvaluationRow[];
  /**
   * True while the caller is still loading rows it will supply via `preloadedEvaluations`. The chart
   * shows a loading state and holds off its own fetch, rather than briefly rendering empty. Only set
   * for groups known (from `evaluation_count`) to fit one page — larger groups fetch immediately.
   */
  preloadPending?: boolean;
}

const CHART_HEIGHT = 360;
const DEFAULT_X_METRIC = 'cost_usd';
const DEFAULT_Y_METRIC = 'latency_ms';

/** Unit-less axis tick labels (units live on the axis label + chart title). Big values are compacted
 * so they don't wrap and collide with the rotated axis title (16000 -> "16K"); small values keep full
 * precision so close cost/score ticks don't all round to the same number (0.05, 0.11 stay distinct). */
const formatAxisTick = (value: number): string =>
  Math.abs(value) >= 1000
    ? value.toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 1 })
    : value.toLocaleString(undefined, { maximumFractionDigits: 3 });

/** Format a metric value for tooltips: cost as USD, latency in ms, evaluator scores as-is. */
const formatMetricValue = (metric: ParetoMetric, value: number): string => {
  if (metric.id === 'cost_usd') {
    return `$${value.toLocaleString(undefined, { maximumFractionDigits: 4 })}`;
  }
  if (metric.id === 'latency_ms') {
    return `${Math.round(value).toLocaleString()} ms`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
};

interface ParetoTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{ payload: ParetoPlotPoint }>;
  xMetric: ParetoMetric;
  yMetric: ParetoMetric;
}

const ParetoTooltip: FC<ParetoTooltipProps> = ({ active, payload, xMetric, yMetric }) => {
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="rounded border border-base bg-surface p-2 shadow-md">
      <Text kind="body/semibold/sm">{point.name}</Text>
      <div className="mt-1 flex flex-col gap-0.5">
        <Text kind="body/regular/xs">
          {xMetric.label}: {formatMetricValue(xMetric, point.x)}
        </Text>
        <Text kind="body/regular/xs">
          {yMetric.label}: {formatMetricValue(yMetric, point.y)}
        </Text>
        {point.onFrontier && (
          <Text kind="body/regular/xs" color="brand">
            On the Pareto frontier
          </Text>
        )}
      </div>
    </div>
  );
};

interface MetricSelectProps {
  label: string;
  value: string;
  metrics: readonly ParetoMetric[];
  onChange: (id: string) => void;
}

const MetricSelect: FC<MetricSelectProps> = ({ label, value, metrics, onChange }) => (
  <label className="flex items-center gap-2">
    <Text kind="body/regular/sm" color="subtle">
      {label}
    </Text>
    <SelectRoot value={value} onValueChange={onChange} size="small">
      <SelectTrigger
        className="w-26"
        size="small"
        aria-label={label}
        // The trigger shows the raw value by default; map it back to the metric's label.
        renderValue={(v) => (typeof v === 'string' && v ? metricLabel(v) : undefined)}
      />
      {/* Keep the dropdown readable even when the trigger is compact/narrow. */}
      <SelectContent className="min-w-48">
        <SelectListbox>
          {metrics.map((metric) => (
            <SelectItem key={metric.id} value={metric.id}>
              {metric.label}
            </SelectItem>
          ))}
        </SelectListbox>
      </SelectContent>
    </SelectRoot>
  </label>
);

/**
 * Cost-vs-accuracy Pareto view for an experiment group: one point per evaluation with the Pareto
 * frontier highlighted. Points come from the group's evaluations (the existing list endpoint, which
 * already carries each evaluation's cost/latency/evaluator rollup means). The two axes are chosen from
 * the group's available metrics (cost, latency, and each evaluator) and are **persisted on the group**
 * — changing a picker saves the selection so it survives reloads and is shared across viewers. Seeds
 * from the group's saved axes, defaulting to cost vs. latency (present for every group).
 */
export const ExperimentGroupParetoChart: FC<ExperimentGroupParetoChartProps> = ({
  workspace,
  group,
  preloadedEvaluations,
  preloadPending = false,
}) => {
  const queryClient = useQueryClient();
  const toast = useToast();

  // Reuse the caller's rows when it already has the whole group loaded. While it's still loading and
  // about to supply them (`preloadPending`), hold off our own fetch and show a loading state instead of
  // rendering empty. Otherwise fetch the evaluations ourselves (in parallel — see the `enabled` flag).
  const hasPreloaded = preloadedEvaluations !== undefined;
  const {
    rows: fetchedRows,
    isLoading: isFetching,
    isError,
  } = useParetoEvaluations(workspace, group.id, { enabled: !hasPreloaded && !preloadPending });
  const points = hasPreloaded ? preloadedEvaluations : fetchedRows;
  const isLoading = hasPreloaded ? false : preloadPending || isFetching;
  const metrics = useMemo(() => deriveParetoMetrics(points), [points]);

  // Selected axes are optimistic local state seeded from the group's saved config (available
  // synchronously from the `group` prop). Changes update the chart immediately and persist below.
  const [xMetricId, setXMetricId] = useState(group.pareto?.x_metric ?? DEFAULT_X_METRIC);
  const [yMetricId, setYMetricId] = useState(group.pareto?.y_metric ?? DEFAULT_Y_METRIC);

  const { mutate: saveGroup, isPending: isSaving } = useUpdateExperimentGroup({
    mutation: {
      onSuccess: () => {
        toast.success('Saved the group default Pareto view.');
        queryClient.invalidateQueries({
          queryKey: getGetExperimentGroupQueryKey(workspace, group.name),
        });
      },
      onError: () => toast.error('Failed to save the Pareto metrics.'),
    },
  });

  // Persist the axes on the group. PUT is a full replace, so send every current field — only `pareto`
  // changes.
  const persistAxes = (xMetric: string, yMetric: string) => {
    saveGroup({
      workspace,
      name: group.name,
      data: {
        name: group.name,
        description: group.description,
        insight_id: group.insight_id,
        summary: group.summary,
        metadata: group.metadata,
        default_sort: group.default_sort,
        pareto: { x_metric: xMetric, y_metric: yMetric },
      },
    });
  };

  // Picking a metric only updates the local view; persisting the group-wide default is an explicit,
  // clearly-labeled action (Save button) so users know a save is shared with everyone.
  const handleXChange = (id: string) => setXMetricId(id);
  const handleYChange = (id: string) => setYMetricId(id);

  const savedX = group.pareto?.x_metric ?? DEFAULT_X_METRIC;
  const savedY = group.pareto?.y_metric ?? DEFAULT_Y_METRIC;
  const hasUnsavedAxes = xMetricId !== savedX || yMetricId !== savedY;

  // Fall back to the first/second metric if a saved id isn't in the current data (e.g. an evaluator
  // that dropped out). Cost and latency are always present, so a fallback always exists.
  const xMetric = metrics.find((m) => m.id === xMetricId) ?? metrics[0];
  const yMetric = metrics.find((m) => m.id === yMetricId) ?? metrics[1] ?? metrics[0];

  const plotPoints = useMemo(
    () => (xMetric && yMetric ? buildParetoPoints(points, xMetric, yMetric) : []),
    [points, xMetric, yMetric]
  );

  // Frontier points are sorted by x so Recharts draws the connecting line along the frontier curve.
  const frontierPoints = useMemo(
    () => plotPoints.filter((p) => p.onFrontier).sort((a, b) => a.x - b.x),
    [plotPoints]
  );
  const dominatedPoints = useMemo(() => plotPoints.filter((p) => !p.onFrontier), [plotPoints]);

  const renderBody = () => {
    if (isError) {
      return <Text kind="body/regular/sm">Could not load the Pareto data for this group.</Text>;
    }
    if (isLoading) {
      return (
        <div aria-busy className="flex h-[360px] items-center justify-center gap-2">
          <Loader2 width={20} height={20} className="animate-spin text-brand" />
          <Text kind="body/regular/sm" color="subtle">
            Loading evaluations…
          </Text>
        </div>
      );
    }
    if (plotPoints.length === 0 || !xMetric || !yMetric) {
      return (
        <Text kind="body/regular/sm" color="subtle">
          No evaluations with both selected metrics to plot.
        </Text>
      );
    }
    return (
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <ScatterChart margin={{ top: 16, right: 24, bottom: 24, left: 16 }}>
          <CartesianGrid stroke="var(--border-color-base)" strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="x"
            name={xMetric.label}
            label={{ value: xMetric.label, position: 'insideBottom', offset: -12 }}
            tickFormatter={formatAxisTick}
            tick={{ fontSize: 11 }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name={yMetric.label}
            label={{ value: yMetric.label, angle: -90, position: 'insideLeft' }}
            tickFormatter={formatAxisTick}
            tick={{ fontSize: 11 }}
          />
          <Tooltip
            cursor={{ strokeDasharray: '3 3' }}
            content={<ParetoTooltip xMetric={xMetric} yMetric={yMetric} />}
          />
          <Scatter
            name="Evaluations"
            data={dominatedPoints}
            fill="var(--text-color-secondary)"
            fillOpacity={0.7}
          />
          <Scatter
            name="Pareto frontier"
            data={frontierPoints}
            fill="var(--border-color-brand)"
            line={{ stroke: 'var(--border-color-brand)' }}
          />
        </ScatterChart>
      </ResponsiveContainer>
    );
  };

  return (
    <div className="flex flex-col gap-3 rounded border border-base bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <Text kind="title/xs">{`${metricLabel(xMetricId)} vs. ${metricLabel(yMetricId)}`}</Text>
        <div className="flex flex-wrap items-center gap-4">
          <MetricSelect
            label="X axis"
            value={xMetric?.id ?? ''}
            metrics={metrics}
            onChange={handleXChange}
          />
          <MetricSelect
            label="Y axis"
            value={yMetric?.id ?? ''}
            metrics={metrics}
            onChange={handleYChange}
          />
          <Button
            kind="primary"
            size="small"
            aria-label={isSaving ? 'Saving' : 'Save as group default'}
            disabled={!hasUnsavedAxes || isSaving}
            onClick={() => persistAxes(xMetricId, yMetricId)}
          >
            {isSaving ? (
              <Loader2 width={16} height={16} className="animate-spin" />
            ) : (
              <Save width={16} height={16} />
            )}
          </Button>
        </div>
      </div>
      {renderBody()}
    </div>
  );
};
