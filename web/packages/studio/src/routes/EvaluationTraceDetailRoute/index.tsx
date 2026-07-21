// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  useGetEvaluation,
  useGetExperimentGroup,
  useGetTrace,
  useListEvaluations,
} from '@nemo/sdk/generated/platform/api';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { type BreadcrumbsItemProps } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { CompareExperimentSelect } from '@studio/routes/EvaluationTraceDetailRoute/CompareExperimentSelect';
import { ExperimentTraceCompare } from '@studio/routes/EvaluationTraceDetailRoute/ExperimentTraceCompare';
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
  const compareWith = searchParams.get(QUERY_PARAMETERS.compareWith);

  const { traceId, experimentGroupName, evaluationName } = useRequiredPathParams([
    ROUTE_PARAMS.traceId,
    ROUTE_PARAMS.experimentGroupName,
    ROUTE_PARAMS.evaluationName,
  ]);

  // Fetch primary evaluation to get dataset_name for filtering sibling evaluations.
  const { data: primaryEvaluation } = useGetEvaluation(workspace, evaluationName);

  // Fetch the experiment group to get its id for the sibling evaluation query.
  const { data: group } = useGetExperimentGroup(workspace, experimentGroupName);

  // List all evaluations in the same group so the compare selector is populated.
  const { data: siblingsPage, isLoading: isLoadingSiblings } = useListEvaluations(
    workspace,
    {
      filter: { experiment_group_id: group?.id },
      page_size: 1000,
    },
    { query: { enabled: Boolean(group?.id) } }
  );

  // Filter to evaluations sharing the same dataset as the primary.
  const comparableEvaluations = useMemo(() => {
    if (!siblingsPage?.data || !primaryEvaluation?.dataset_name) return [];
    return siblingsPage.data.filter((e) => e.dataset_name === primaryEvaluation.dataset_name);
  }, [siblingsPage, primaryEvaluation]);

  // Fetch the primary trace to extract test_case_id (needed to look up the compare session).
  const { data: primaryTrace, isLoading: isPrimaryTraceLoading } = useGetTrace(workspace, traceId, {
    mode: 'summary',
  });
  const testCaseId = primaryTrace?.experiment_context?.test_case_id;

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

  const handleCompareChange = (selectedEvaluationName: string) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        next.set(QUERY_PARAMETERS.compareWith, selectedEvaluationName);
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
    <div className="flex items-center gap-density-md">
      <CompareExperimentSelect
        evaluations={comparableEvaluations}
        currentEvaluationName={evaluationName}
        value={compareWith}
        onChange={handleCompareChange}
        isLoading={isLoadingSiblings}
      />
      {compareWith && (
        <button className="text-sm text-content-link hover:underline" onClick={handleClearCompare}>
          Clear
        </button>
      )}
    </div>
  );

  if (compareWith) {
    return (
      <ExperimentTraceCompare
        workspace={workspace}
        experimentGroupName={experimentGroupName}
        primaryEvaluationName={evaluationName}
        primaryTraceId={traceId}
        compareEvaluationName={compareWith}
        testCaseId={testCaseId}
        isPrimaryTraceLoading={isPrimaryTraceLoading}
        slotHeaderActions={compareSelector}
        onClose={handleClearCompare}
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
