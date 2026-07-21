// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { useListEvaluationSessions } from '@nemo/sdk/generated/platform/api';
import type { EvaluationSessionResponse } from '@nemo/sdk/generated/platform/schema';
import { Button, Divider, Flex, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { IntakeTraceDetailView } from '@studio/components/IntakeDetail/TraceDetailView';
import { type SlotHeaderRenderProp } from '@studio/components/IntakeDetail/TraceSpanAccordions';
import { Loading } from '@studio/components/Layouts/Loading';
import {
  type BreadcrumbsItemProps,
  useBreadcrumbs,
} from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { useCompareSession } from '@studio/routes/EvaluationTraceDetailRoute/useCompareSession';
import { getExperimentGroupDetailRoute, getExperimentRoute } from '@studio/routes/utils';
import { CircleAlert, ChevronsDownUp, ChevronsUpDown, X } from 'lucide-react';
import { type FC, useEffect, useState } from 'react';

interface ExperimentTraceCompareProps {
  workspace: string;
  experimentGroupName: string;
  primaryEvaluationName: string;
  primaryTraceId: string;
  compareEvaluationName: string;
  testCaseId: string | null | undefined;
  isPrimaryTraceLoading: boolean;
  slotHeaderActions?: React.ReactNode;
  onClose: () => void;
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

const pickCorrectness = (scores?: EvaluationSessionResponse['evaluator_scores']): number | null => {
  if (!scores) return null;
  return scores['composite_score'] ?? scores['correctness'] ?? Object.values(scores)[0] ?? null;
};

// ── Column slot render prop ───────────────────────────────────────────────────

/**
 * Builds the slotSpanHeader render prop for a compare column.
 * Renders: evaluation name + collapse/expand/close buttons (top row),
 * then a metrics card, all passed into TraceSpanAccordions as its header slot.
 */
const makeColumnSlot =
  (
    evaluationName: string,
    session: EvaluationSessionResponse | undefined,
    onClose: () => void
  ): SlotHeaderRenderProp =>
  ({ expandAll, collapseAll }) => {
    const correctness = pickCorrectness(session?.evaluator_scores);
    return (
      <Stack gap="density-md">
        {/* Heading row */}
        <Flex align="center" justify="between" gap="density-sm">
          <Text kind="title/sm">{evaluationName}</Text>
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
            <Button
              kind="tertiary"
              type="button"
              aria-label="Close comparison"
              title="Close comparison"
              onClick={onClose}
            >
              <X size={16} aria-hidden />
            </Button>
          </Flex>
        </Flex>

        {/* Metrics card */}
        <div className="rounded-sm border border-base bg-surface-raised p-density-lg">
          <Flex align="stretch" justify="between" gap="density-2xl">
            <KVPair
              label="Correctness"
              value={correctness != null ? `${Math.round(correctness * 100)}%` : undefined}
              orientation="vertical"
              attributes={{ value: { kind: 'title/sm' } }}
            />
            <Flex align="stretch" gap="density-lg">
              <Divider orientation="vertical" className="grow-0 self-stretch" />
              <KVPair label="Latency" value={fmtMs(session?.latency_ms)} orientation="vertical" />
              <Divider orientation="vertical" className="grow-0 self-stretch" />
              <KVPair
                label="Tkns In"
                value={fmtNum(session?.input_tokens)}
                orientation="vertical"
              />
              <Divider orientation="vertical" className="grow-0 self-stretch" />
              <KVPair
                label="Tkns Out"
                value={fmtNum(session?.output_tokens)}
                orientation="vertical"
              />
              <Divider orientation="vertical" className="grow-0 self-stretch" />
              <KVPair
                label="Cached Tkns"
                value={fmtNum(session?.cached_tokens)}
                orientation="vertical"
              />
            </Flex>
          </Flex>
        </div>
      </Stack>
    );
  };

// ── Column ────────────────────────────────────────────────────────────────────

const CompareTraceColumn: FC<{
  workspace: string;
  traceId: string;
  slotSpanHeader: SlotHeaderRenderProp;
}> = ({ workspace, traceId, slotSpanHeader }) => {
  const [linkedSpanId, setLinkedSpanId] = useState<string | null>(null);
  return (
    <IntakeTraceDetailView
      workspace={workspace}
      traceId={traceId}
      disableBreadcrumbs
      hidePageHeader
      forceListView
      linkedSpanId={linkedSpanId}
      onLinkedSpanIdChange={setLinkedSpanId}
      slotSpanHeader={slotSpanHeader}
    />
  );
};

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
  primaryEvaluationName,
  primaryTraceId,
  compareEvaluationName,
  testCaseId,
  isPrimaryTraceLoading,
  slotHeaderActions,
  onClose,
}) => {
  const { setBreadcrumbs } = useBreadcrumbs();

  const breadcrumbs: BreadcrumbsItemProps[] = [
    { slotLabel: 'Experiment Groups', href: getExperimentRoute(workspace) },
    {
      slotLabel: experimentGroupName,
      href: getExperimentGroupDetailRoute(workspace, experimentGroupName),
    },
    { slotLabel: 'Test case comparison' },
  ];

  useEffect(() => {
    setBreadcrumbs(breadcrumbs);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setBreadcrumbs, workspace, experimentGroupName]);

  const { data: primarySessionPage } = useListEvaluationSessions(
    workspace,
    primaryEvaluationName,
    { filter: { test_case_id: testCaseId ?? '' }, page_size: 1 },
    { query: { enabled: Boolean(testCaseId) && !isPrimaryTraceLoading } }
  );
  const primarySession = primarySessionPage?.data?.[0];

  const compareState = useCompareSession({
    workspace,
    compareEvaluationName,
    testCaseId,
    isTestCaseIdLoading: isPrimaryTraceLoading,
  });

  const renderRightColumn = () => {
    switch (compareState.status) {
      case 'loading':
        return <Loading description="Loading comparison trace…" />;
      case 'no-test-case-id':
        return <CompareNoTestCaseId />;
      case 'not-found':
        return <CompareNotFound testCaseId={compareState.testCaseId} />;
      case 'found':
        return (
          <CompareTraceColumn
            key={compareState.session.trace_id}
            workspace={workspace}
            traceId={compareState.session.trace_id}
            slotSpanHeader={makeColumnSlot(compareEvaluationName, compareState.session, onClose)}
          />
        );
    }
  };

  return (
    <AccessibleTitle title="Test case comparison">
      <Stack className="h-full min-h-0" gap="0">
        <div className="shrink-0 border-b border-base px-density-2xl py-density-lg">
          <PageHeader
            className="p-0"
            slotHeading="Test case comparison"
            slotDescription="Compare multiple test cases from compatible evaluations"
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
                slotSpanHeader={makeColumnSlot(primaryEvaluationName, primarySession, onClose)}
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
