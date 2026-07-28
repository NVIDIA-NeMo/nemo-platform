// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LogViewer } from '@nemo/common/src/components/LogViewer';
import {
  useAnonymizerGetRunJob,
  useAnonymizerGetRunJobLogs,
  useAnonymizerListRunJobResults,
} from '@nemo/sdk/generated/anonymizer/api';
import { Banner, Grid, PageHeader, Panel, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { AnonymizerJobActionsMenu } from '@studio/components/AnonymizerJobActionsMenu';
import { ANONYMIZER_ENABLED } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { JobSummaryPanel } from '@studio/routes/AnonymizerJobDetailRoute/components/JobSummaryPanel';
import { ResultsPanel } from '@studio/routes/AnonymizerJobDetailRoute/components/ResultsPanel';
import { ANONYMIZER_POLLING_INTERVAL_MS } from '@studio/routes/AnonymizerJobDetailRoute/util';
import { getWorkspaceAnonymizerRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { isJobTerminated } from '@studio/util/safeSynthesizer';
import type { FC } from 'react';
import { useNavigate } from 'react-router-dom';

export const AnonymizerJobDetailRoute: FC | null = ANONYMIZER_ENABLED
  ? () => {
      const workspace = useWorkspaceFromPath();
      const navigate = useNavigate();
      const { anonymizerJobName } = useRequiredPathParams([ROUTE_PARAMS.anonymizerJobName]);

      const {
        data: job,
        isLoading: isLoadingJob,
        error,
      } = useAnonymizerGetRunJob(workspace, anonymizerJobName, {
        query: {
          refetchInterval: (query) =>
            isJobTerminated(query.state.data?.status) ? false : ANONYMIZER_POLLING_INTERVAL_MS,
        },
      });

      const isTerminal = isJobTerminated(job?.status);

      const { data: results, isLoading: isLoadingResults } = useAnonymizerListRunJobResults(
        workspace,
        anonymizerJobName,
        { query: { enabled: isTerminal } }
      );

      const { data: logs, isLoading: isLoadingLogs } = useAnonymizerGetRunJobLogs(
        workspace,
        anonymizerJobName,
        undefined,
        { query: { refetchInterval: isTerminal ? false : ANONYMIZER_POLLING_INTERVAL_MS } }
      );

      useBreadcrumbs({
        items: [
          { href: getWorkspaceAnonymizerRoute(workspace), slotLabel: 'Anonymizer' },
          { slotLabel: anonymizerJobName },
        ],
      });

      return (
        <AccessibleTitle title={`Anonymizer Job - ${anonymizerJobName}`}>
          <Stack className="h-full w-full overflow-auto" gap="density-2xl" padding="density-2xl">
            <PageHeader
              className="p-0"
              slotHeading={anonymizerJobName}
              slotActions={
                job ? (
                  <AnonymizerJobActionsMenu
                    job={job}
                    onDeleted={() => navigate(getWorkspaceAnonymizerRoute(workspace))}
                  />
                ) : null
              }
            />

            {error ? (
              <Banner kind="inline" status="error">
                Could not load this job.
              </Banner>
            ) : (
              <Stack gap="density-2xl" className="w-full min-w-0">
                <Grid cols={{ base: 1, xl: 2 }} gap="density-2xl">
                  {job && !isLoadingJob ? <JobSummaryPanel job={job} /> : null}
                  <ResultsPanel
                    workspace={workspace}
                    jobName={anonymizerJobName}
                    results={results?.data ?? []}
                    isLoading={isLoadingResults}
                    isTerminal={isTerminal}
                  />
                </Grid>
                <Panel slotHeading="Logs" elevation="high" density="compact">
                  <LogViewer
                    logs={logs?.data ?? []}
                    isLoading={isLoadingLogs}
                    downloadFilename={`anonymizer-${anonymizerJobName}-logs.txt`}
                  />
                </Panel>
              </Stack>
            )}
          </Stack>
        </AccessibleTitle>
      );
    }
  : null;
