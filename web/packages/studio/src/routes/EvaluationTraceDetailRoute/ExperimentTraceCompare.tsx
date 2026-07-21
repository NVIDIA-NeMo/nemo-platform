// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { IntakeTraceDetailView } from '@studio/components/IntakeDetail/TraceDetailView';
import { type SlotHeaderRenderProp } from '@studio/components/IntakeDetail/TraceSpanAccordions';
import { Loading } from '@studio/components/Layouts/Loading';
import {
  type BreadcrumbsItemProps,
  useBreadcrumbs,
} from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { runLabel } from '@studio/routes/EvaluationTraceDetailRoute/runLabel';
import { getExperimentGroupDetailRoute, getExperimentRoute } from '@studio/routes/utils';
import { CircleAlert, ChevronsDownUp, ChevronsUpDown } from 'lucide-react';
import { type FC, useEffect } from 'react';

interface ExperimentTraceCompareProps {
  workspace: string;
  experimentGroupName: string;
  testCaseId: string | null | undefined;
  primaryTraceId: string;
  primarySession: EvaluationSessionResponse | undefined;
  compareTraceId: string;
  compareSession: EvaluationSessionResponse | undefined;
  /** True while the group's test-case runs are still loading. */
  isRunsLoading: boolean;
  slotHeaderActions?: React.ReactNode;
}

// ── Metrics helpers ───────────────────────────────────────────────────────────

const fmtNum = (n?: number | null) => {
  if (n == null) return '—';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1_000)}k`;
  return String(Math.round(n));
};

const fmtMs = (ms?: number | null) => {
  if (ms == null) return '—';
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1_000);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
};

const fmtCost = (usd?: number | null) => {
  if (usd == null) return '—';
  if (usd === 0) return '$0';
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
};

/** Evaluator means in the 0–1 range read as percentages; anything else is a raw scale. */
const fmtScore = (v: number) => (v >= 0 && v <= 1 ? `${Math.round(v * 100)}%` : v.toFixed(2));

/** The per-session metrics shown in each column's card, in display order. */
const sessionMetrics = (session: EvaluationSessionResponse | undefined) => [
  { label: 'Cost', value: fmtCost(session?.cost_total_usd) },
  { label: 'Latency', value: fmtMs(session?.latency_ms) },
  { label: 'Tkns In', value: fmtNum(session?.input_tokens) },
  { label: 'Tkns Out', value: fmtNum(session?.output_tokens) },
  { label: 'Cached Tkns', value: fmtNum(session?.cached_tokens) },
  ...Object.entries(session?.evaluator_scores ?? {}).map(([name, score]) => ({
    label: name,
    value: fmtScore(score),
  })),
];

// ── Column slot render prop ───────────────────────────────────────────────────

/**
 * Builds the slotSpanHeader render prop for a compare column: the run label +
 * expand/collapse controls, then a card of this run's per-session metrics.
 */
const makeColumnSlot =
  (label: string, session: EvaluationSessionResponse | undefined): SlotHeaderRenderProp =>
  ({ expandAll, collapseAll }) => (
    <Stack gap="density-md">
      {/* Heading row */}
      <Flex align="center" justify="between" gap="density-sm">
        <Text kind="title/sm">{label}</Text>
        <Flex align="center" gap="density-xs">
          <Button
            kind="tertiary"
            size="tiny"
            type="button"
            aria-label="Collapse all"
            title="Collapse all"
            onClick={collapseAll}
          >
            <ChevronsDownUp size={14} aria-hidden />
          </Button>
          <Button
            kind="tertiary"
            size="tiny"
            type="button"
            aria-label="Expand all"
            title="Expand all"
            onClick={expandAll}
          >
            <ChevronsUpDown size={14} aria-hidden />
          </Button>
        </Flex>
      </Flex>

      {/* Per-session metrics card */}
      <div className="rounded-sm border border-base bg-surface-raised p-density-lg">
        <Flex align="stretch" gap="density-2xl" className="flex-wrap">
          {sessionMetrics(session).map((m) => (
            <KVPair key={m.label} label={m.label} value={m.value} orientation="vertical" />
          ))}
        </Flex>
      </div>
    </Stack>
  );

// ── Column ────────────────────────────────────────────────────────────────────

const CompareTraceColumn: FC<{
  workspace: string;
  traceId: string;
  slotSpanHeader: SlotHeaderRenderProp;
}> = ({ workspace, traceId, slotSpanHeader }) => (
  <IntakeTraceDetailView
    workspace={workspace}
    traceId={traceId}
    disableBreadcrumbs
    hidePageHeader
    forceListView
    linkedSpanId={null}
    onLinkedSpanIdChange={() => {}}
    slotSpanHeader={slotSpanHeader}
  />
);

const CompareNotFound: FC<{ testCaseId: string }> = ({ testCaseId }) => (
  <div className="flex h-full flex-col items-center justify-center gap-3 p-density-2xl text-center">
    <CircleAlert className="h-10 w-10 text-status-warning" aria-hidden />
    <p className="font-semibold text-content-primary">Test case not available</p>
    <p className="max-w-sm text-sm text-content-secondary">
      Test case <code className="font-mono">{testCaseId}</code> was not run for this evaluation.
    </p>
  </div>
);

const CompareNoTestCaseId: FC = () => (
  <div className="flex h-full flex-col items-center justify-center gap-3 p-density-2xl text-center">
    <CircleAlert className="h-10 w-10 text-status-warning" aria-hidden />
    <p className="font-semibold text-content-primary">Cannot compare</p>
    <p className="max-w-sm text-sm text-content-secondary">
      This trace has no test case ID. Comparison requires a producer-supplied test case ID.
    </p>
  </div>
);

// ── Main component ────────────────────────────────────────────────────────────

export const ExperimentTraceCompare: FC<ExperimentTraceCompareProps> = ({
  workspace,
  experimentGroupName,
  testCaseId,
  primaryTraceId,
  primarySession,
  compareTraceId,
  compareSession,
  isRunsLoading,
  slotHeaderActions,
}) => {
  const { setBreadcrumbs } = useBreadcrumbs();

  useEffect(() => {
    const breadcrumbs: BreadcrumbsItemProps[] = [
      { slotLabel: 'Experiment Groups', href: getExperimentRoute(workspace) },
      {
        slotLabel: experimentGroupName,
        href: getExperimentGroupDetailRoute(workspace, experimentGroupName),
      },
      { slotLabel: 'Test case comparison' },
    ];
    setBreadcrumbs(breadcrumbs);
  }, [setBreadcrumbs, workspace, experimentGroupName]);

  const heading = testCaseId
    ? `Test case comparison — Test case ${testCaseId}`
    : 'Test case comparison';

  const renderRightColumn = () => {
    if (!testCaseId) return <CompareNoTestCaseId />;
    if (compareSession) {
      return (
        <CompareTraceColumn
          key={compareTraceId}
          workspace={workspace}
          traceId={compareTraceId}
          slotSpanHeader={makeColumnSlot(runLabel(compareSession), compareSession)}
        />
      );
    }
    if (isRunsLoading) return <Loading description="Loading comparison run…" />;
    return <CompareNotFound testCaseId={testCaseId} />;
  };

  return (
    <AccessibleTitle title="Test case comparison">
      <Stack className="h-full min-h-0" gap="0">
        <div className="shrink-0 border-b border-base px-density-2xl py-density-lg">
          <PageHeader
            className="p-0"
            slotHeading={heading}
            slotDescription="See how this test case performed across different runs"
            slotActions={slotHeaderActions}
          />
        </div>
        <div className="flex min-h-0 flex-1 divide-x divide-base">
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-auto">
              <CompareTraceColumn
                key={primaryTraceId}
                workspace={workspace}
                traceId={primaryTraceId}
                slotSpanHeader={makeColumnSlot(
                  primarySession ? runLabel(primarySession) : '—',
                  primarySession
                )}
              />
            </div>
          </div>
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-auto">{renderRightColumn()}</div>
          </div>
        </div>
      </Stack>
    </AccessibleTitle>
  );
};
