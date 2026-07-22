// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  useGetExperimentGroup,
  useGetTrace,
  useListEvaluations,
} from '@nemo/sdk/generated/platform/api';
import { Flex } from '@nvidia/foundations-react-core';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { type BreadcrumbsItemProps } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { CompareRunSelect } from '@studio/routes/EvaluationTraceDetailRoute/CompareRunSelect';
import { ExperimentTraceCompare } from '@studio/routes/EvaluationTraceDetailRoute/ExperimentTraceCompare';
import { useTestCaseRuns } from '@studio/routes/EvaluationTraceDetailRoute/useTestCaseRuns';
import { IntakeTraceDetailContent } from '@studio/routes/IntakeTraceDetailRoute';
import {
  getEvaluationDetailRoute,
  getEvaluationTraceDetailRoute,
  getExperimentGroupDetailRoute,
  getExperimentRoute,
} from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

export const EvaluationTraceDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  // compareWith carries the trace_id of the run to show in the right column.
  const compareWith = searchParams.get(QUERY_PARAMETERS.compareWith);

  const { traceId, experimentGroupName, evaluationName } = useRequiredPathParams([
    ROUTE_PARAMS.traceId,
    ROUTE_PARAMS.experimentGroupName,
    ROUTE_PARAMS.evaluationName,
  ]);

  // The experiment group's id scopes the sibling evaluations we fan out over.
  const { data: group, isLoading: isGroupLoading } = useGetExperimentGroup(
    workspace,
    experimentGroupName
  );

  const { data: evaluationsPage, isLoading: isEvaluationsLoading } = useListEvaluations(
    workspace,
    { filter: { experiment_group_id: group?.id }, page_size: 1000 },
    { query: { enabled: Boolean(group?.id) } }
  );
  const evaluationNames = useMemo(
    () => evaluationsPage?.data?.map((e) => e.name) ?? [],
    [evaluationsPage]
  );

  // The primary trace supplies the test_case_id every run is matched on.
  const { data: primaryTrace, isLoading: isTraceLoading } = useGetTrace(workspace, traceId, {
    mode: 'summary',
  });
  const testCaseId = primaryTrace?.experiment_context?.test_case_id;

  // Every run of this test case across the group (Option A: FE fan-out per evaluation).
  const { runs, isLoading: isRunsLoading } = useTestCaseRuns({
    workspace,
    evaluationNames,
    testCaseId,
  });

  // The selector is "loading" through the whole chain: group -> evaluations -> trace -> runs.
  const isRunsSelectorLoading =
    isGroupLoading || isEvaluationsLoading || isTraceLoading || isRunsLoading;

  const primarySession = runs.find((r) => r.trace_id === traceId);
  const compareSession = compareWith ? runs.find((r) => r.trace_id === compareWith) : undefined;

  const parentBreadcrumbs = useMemo<BreadcrumbsItemProps[]>(
    () => [
      { slotLabel: 'Experiment Groups', href: getExperimentRoute(workspace) },
      {
        slotLabel: experimentGroupName,
        href: getExperimentGroupDetailRoute(workspace, experimentGroupName),
      },
      {
        slotLabel: evaluationName,
        href: getEvaluationDetailRoute(workspace, experimentGroupName, evaluationName),
      },
    ],
    [workspace, experimentGroupName, evaluationName]
  );

  const handleCompareChange = (selectedTraceId: string) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set(QUERY_PARAMETERS.compareWith, selectedTraceId);
        return next;
      },
      { replace: false }
    );
  };

  const handleClearCompare = () => {
    navigate(
      getEvaluationTraceDetailRoute(workspace, experimentGroupName, evaluationName, traceId)
    );
  };

  const compareSelector = (
    <Flex align="center" gap="density-md">
      <CompareRunSelect
        runs={runs}
        currentTraceId={traceId}
        value={compareWith}
        onChange={handleCompareChange}
        isLoading={isRunsSelectorLoading}
      />
      {compareWith && (
        <button
          className="text-sm text-color-secondary hover:underline"
          onClick={handleClearCompare}
        >
          Clear
        </button>
      )}
    </Flex>
  );

  if (compareWith) {
    return (
      <ExperimentTraceCompare
        workspace={workspace}
        experimentGroupName={experimentGroupName}
        testCaseId={testCaseId}
        primaryTraceId={traceId}
        primarySession={primarySession}
        compareTraceId={compareWith}
        compareSession={compareSession}
        isRunsLoading={isRunsLoading}
        slotHeaderActions={compareSelector}
      />
    );
  }

  return (
    <div className="h-full overflow-auto">
      <IntakeTraceDetailContent
        traceId={traceId}
        parentBreadcrumbs={parentBreadcrumbs}
        showTestCaseTitle
        slotPageHeaderActions={compareSelector}
      />
    </div>
  );
};
