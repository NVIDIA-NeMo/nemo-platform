// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useGetEvaluation } from '@nemo/sdk/generated/platform/api';
import { Badge, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { EvaluationSessionsDataView } from '@studio/components/dataViews/EvaluationSessionsDataView';
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
  const { data: experiment } = useGetEvaluation(workspace, evaluationName);

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
        <PageHeader
          className="p-0"
          slotHeading={evaluationName}
          slotDescription={experiment?.description || undefined}
        />
        <EvaluationDetailMetrics evaluationName={evaluationName} />
        <div className="flex flex-col gap-4 border-t border-base pt-4">
          <div className="flex items-center gap-3">
            <Text kind="title/sm">Test cases</Text>
            {experiment?.run_count !== undefined && (
              <Badge color="gray" kind="solid" className="text-sm">
                {experiment.run_count}
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
