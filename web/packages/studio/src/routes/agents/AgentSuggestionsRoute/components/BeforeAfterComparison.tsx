// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  Badge,
  Block,
  Flex,
  Stack,
  TableBody,
  TableDataCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
  Text,
} from '@nvidia/foundations-react-core';
import {
  EVAL_STATUS_COLOR,
  EVAL_STATUS_LABEL,
} from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import type {
  EvalRunResult,
  EvalScore,
  EvalUiState,
  ProfilerStats,
} from '@studio/routes/agents/AgentSuggestionsRoute/types';
import { ArrowRight } from 'lucide-react';
import { type FC, memo } from 'react';

interface ComparisonRow {
  label: string;
  before: number | null;
  after: number | null;
  /** Improvement direction: scores go up, tokens/latency go down. */
  higherIsBetter: boolean;
  format: (n: number) => string;
}

const scoreByEvaluator = (scores: EvalScore[], evaluator: string): number | null => {
  const hit = scores.find((s) => s.evaluator === evaluator);
  return hit ? hit.averageScore : null;
};

const formatScore = (n: number): string => n.toFixed(2);
const formatTokens = (n: number): string => Math.round(n).toLocaleString();
const formatSeconds = (n: number): string => `${n.toFixed(2)} s`;

// null diff (a side missing) or a negligible change renders neutral.
const DELTA_EPSILON = 1e-9;

const deltaColor = (
  before: number | null,
  after: number | null,
  higherIsBetter: boolean
): 'green' | 'red' | 'gray' => {
  if (before === null || after === null) return 'gray';
  const diff = after - before;
  if (Math.abs(diff) < DELTA_EPSILON) return 'gray';
  const improved = higherIsBetter ? diff > 0 : diff < 0;
  return improved ? 'green' : 'red';
};

const formatDelta = (row: ComparisonRow): string => {
  if (row.before === null || row.after === null) return '—';
  const diff = row.after - row.before;
  if (Math.abs(diff) < DELTA_EPSILON) return '±0';
  // toLocaleString / toFixed already carry a leading '-' for negatives.
  return `${diff >= 0 ? '+' : ''}${row.format(diff)}`;
};

const formatCell = (row: ComparisonRow, value: number | null): string =>
  value === null ? '—' : row.format(value);

// Union of evaluator names across both runs, preserving the optimized run's
// order first (recall is listed first in the phishing eval) then any extras.
const evaluatorOrder = (after: EvalScore[], before: EvalScore[]): string[] => {
  const order: string[] = [];
  const seen = new Set<string>();
  for (const s of [...after, ...before]) {
    if (seen.has(s.evaluator)) continue;
    seen.add(s.evaluator);
    order.push(s.evaluator);
  }
  return order;
};

const buildRows = (
  before: EvalRunResult | null,
  afterScores: EvalScore[],
  afterProfiler: ProfilerStats | null
): ComparisonRow[] => {
  const beforeScores = before?.scores ?? [];
  const beforeProfiler = before?.profiler ?? null;
  const rows: ComparisonRow[] = [];

  for (const evaluator of evaluatorOrder(afterScores, beforeScores)) {
    rows.push({
      label: evaluator,
      before: scoreByEvaluator(beforeScores, evaluator),
      after: scoreByEvaluator(afterScores, evaluator),
      higherIsBetter: true,
      format: formatScore,
    });
  }

  const costRows: Array<{
    label: string;
    pick: (p: ProfilerStats) => number | null;
    format: (n: number) => string;
  }> = [
    { label: 'Avg tokens / item', pick: (p) => p.avgTotalTokens, format: formatTokens },
    { label: 'LLM latency (p95)', pick: (p) => p.llmLatencyP95Seconds, format: formatSeconds },
    {
      label: 'Workflow runtime (p95)',
      pick: (p) => p.workflowRuntimeP95Seconds,
      format: formatSeconds,
    },
  ];
  for (const cost of costRows) {
    const beforeVal = beforeProfiler ? cost.pick(beforeProfiler) : null;
    const afterVal = afterProfiler ? cost.pick(afterProfiler) : null;
    // Skip a cost row entirely when neither run produced it (no profiler data).
    if (beforeVal === null && afterVal === null) continue;
    rows.push({
      label: cost.label,
      before: beforeVal,
      after: afterVal,
      higherIsBetter: false,
      format: cost.format,
    });
  }

  return rows;
};

interface RunHeaderProps {
  title: string;
  agentName: string;
  status: EvalUiState['status'];
}

const RunHeader: FC<RunHeaderProps> = ({ title, agentName, status }) => (
  <Stack gap="density-xxs">
    <Flex align="center" gap="density-xs" wrap="wrap">
      <Text kind="label/semibold/sm">{title}</Text>
      <Badge kind="outline" color={EVAL_STATUS_COLOR[status]}>
        {EVAL_STATUS_LABEL[status]}
      </Badge>
    </Flex>
    <Text kind="body/regular/xs" color="secondary">
      {agentName}
    </Text>
  </Stack>
);

interface BeforeAfterComparisonProps {
  evalState: EvalUiState;
}

/**
 * Side-by-side original-vs-optimized comparison rendered under a model
 * optimization suggestion once it's been applied. Quality metrics (recall,
 * precision, …) show ↑ as an improvement; cost metrics (tokens, latency) show
 * ↓ as an improvement. Missing values (a run still in flight or without the
 * profiler plugin) render as "—" so the table never blocks on partial data.
 */
export const BeforeAfterComparison: FC<BeforeAfterComparisonProps> = memo(({ evalState }) => {
  const baseline = evalState.baseline ?? null;
  const rows = buildRows(baseline, evalState.scores, evalState.profiler ?? null);

  return (
    <Stack gap="density-sm" data-testid="before-after-comparison" className="mt-density-sm">
      <Flex align="center" gap="density-md" wrap="wrap">
        <RunHeader
          title="Before"
          agentName={baseline?.agentName ?? 'Original'}
          status={baseline?.status ?? 'unknown'}
        />
        <ArrowRight size={16} className="text-secondary" />
        <RunHeader title="After" agentName={evalState.siblingAgentName} status={evalState.status} />
      </Flex>

      {baseline?.error && (
        <Text kind="body/regular/sm" color="danger">
          Baseline: {baseline.error}
        </Text>
      )}
      {evalState.error && (
        <Text kind="body/regular/sm" color="danger">
          Optimized: {evalState.error}
        </Text>
      )}

      {rows.length > 0 && (
        <Block className="overflow-x-auto">
          <TableRoot density="compact" layout="auto" className="w-full">
            <TableHead>
              <TableRow>
                <TableHeaderCell align="left">Metric</TableHeaderCell>
                <TableHeaderCell align="right">Before</TableHeaderCell>
                <TableHeaderCell align="right">After</TableHeaderCell>
                <TableHeaderCell align="right">Δ</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row) => (
                <TableRow key={row.label}>
                  <TableDataCell align="left">
                    <Text kind="body/regular/sm">{row.label}</Text>
                  </TableDataCell>
                  <TableDataCell align="right">
                    <Text kind="body/regular/sm" color="secondary">
                      {formatCell(row, row.before)}
                    </Text>
                  </TableDataCell>
                  <TableDataCell align="right">
                    <Text kind="body/semibold/sm">{formatCell(row, row.after)}</Text>
                  </TableDataCell>
                  <TableDataCell align="right">
                    <Badge
                      kind="outline"
                      color={deltaColor(row.before, row.after, row.higherIsBetter)}
                    >
                      {formatDelta(row)}
                    </Badge>
                  </TableDataCell>
                </TableRow>
              ))}
            </TableBody>
          </TableRoot>
        </Block>
      )}
    </Stack>
  );
});
