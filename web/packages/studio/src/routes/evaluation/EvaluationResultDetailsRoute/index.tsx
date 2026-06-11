// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PlatformJobTerminalStatuses } from '@nemo/common/src/constants/query';
import { useEvaluatorGetEvaluateJob } from '@nemo/sdk/generated/evaluator/api';
import { Flex, PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { DetailsPanel } from '@studio/components/evaluation/Jobs/DetailsPanel';
import { ResultsPanel } from '@studio/components/evaluation/Jobs/ResultsPanel';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getEvaluationResultsRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { FC } from 'react';

const isTerminal = (status?: string) =>
  !!status && PlatformJobTerminalStatuses.includes(status as never);

export const EvaluationResultDetailsRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { id } = useRequiredPathParams([ROUTE_PARAMS.evaluationJobId]);

  const { data: job, error } = useEvaluatorGetEvaluateJob(workspace, id, {
    query: {
      refetchOnMount: 'always',
      refetchInterval: (query) => {
        const status = query.state.data?.status;
        return isTerminal(status) ? false : 5000;
      },
    },
  });

  useBreadcrumbs({
    items: [
      {
        href: getEvaluationResultsRoute(workspace),
        slotLabel: 'Evaluations',
      },
      {
        slotLabel: job?.name ?? id,
      },
    ],
  });

  return (
    <AccessibleTitle title={`Evaluation ${job?.name ?? id}`}>
      <Stack className="overflow-auto" gap="density-2xl" padding="density-2xl">
        <Flex align="center" justify="center" className="w-full">
          <Stack className="w-full max-w-[1200px]" gap="density-2xl">
            <PageHeader className="p-0" slotHeading={job?.name ?? id} />
            <DetailsPanel evaluationJob={job} error={!!error} />
            <ResultsPanel workspace={workspace} jobName={id} status={job?.status} />
          </Stack>
        </Flex>
      </Stack>
    </AccessibleTitle>
  );
};
