// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useGetEvaluation, useGetExperimentGroup } from '@nemo/sdk/generated/platform/api';
import { Badge, Flex, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { useOptimizerGetInsight } from '@studio/api/optimizer';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { EvaluationSessionsDataView } from '@studio/components/dataViews/EvaluationSessionsDataView';
import { DescriptionPanel } from '@studio/components/DescriptionPanel';
import { OriginatingInsightLink } from '@studio/components/OriginatingInsightLink';
import { OPTIMIZER_ENABLED } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { EvaluationDetailMetrics } from '@studio/routes/EvaluationDetailRoute/EvaluationDetailMetrics';
import { getExperimentGroupDetailRoute, getExperimentRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { type FC } from 'react';

export const EvaluationDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { experimentGroupName, evaluationName } = useRequiredPathParams([
    ROUTE_PARAMS.experimentGroupName,
    ROUTE_PARAMS.evaluationName,
  ]);
  const { data: evaluation } = useGetEvaluation(workspace, evaluationName);
  // Evaluations reach their originating insight through the owning group's insight_id.
  const { data: experimentGroup } = useGetExperimentGroup(workspace, experimentGroupName);
  const insightId = experimentGroup?.insight_id ?? '';
  const { data: insight } = useOptimizerGetInsight(workspace, insightId, {
    query: { enabled: OPTIMIZER_ENABLED && Boolean(insightId) },
  });
  const showInsightCard = Boolean(insight?.description);

  useBreadcrumbs({
    items: [
      { href: getExperimentRoute(workspace), slotLabel: 'Experiment Groups' },
      {
        href: getExperimentGroupDetailRoute(workspace, experimentGroupName),
        slotLabel: experimentGroupName,
      },
      { slotLabel: evaluationName },
    ],
  });

  return (
    <AccessibleTitle title={evaluationName}>
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader className="p-0" slotHeading={evaluationName} />
        <EvaluationDetailMetrics evaluationName={evaluationName} />
        {evaluation?.description || showInsightCard ? (
          <Flex className="items-start gap-density-lg">
            {evaluation?.description ? (
              <DescriptionPanel
                title="Evaluation description"
                description={evaluation.description}
              />
            ) : null}
            {showInsightCard ? (
              <DescriptionPanel
                title="Insight description"
                description={insight?.description ?? ''}
                slotTitleEnd={<OriginatingInsightLink insightId={insightId} />}
              />
            ) : null}
          </Flex>
        ) : null}
        <div className="flex flex-col gap-4 border-t border-base pt-4">
          <div className="flex items-center gap-3">
            <Text kind="title/sm">Test cases</Text>
            {evaluation?.run_count !== undefined && (
              <Badge color="gray" kind="solid" className="text-sm">
                {evaluation.run_count}
              </Badge>
            )}
          </div>
          <EvaluationSessionsDataView
            evaluationName={evaluationName}
            experimentGroupName={experimentGroupName}
          />
        </div>
      </Stack>
    </AccessibleTitle>
  );
};
