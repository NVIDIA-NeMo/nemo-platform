// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AccordionPanel } from '@nemo/common/src/components/AccordionPanel';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import type { PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';
import {
  Block,
  Button,
  Flex,
  Grid,
  PageHeader,
  Panel,
  Spinner,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import {
  aggregateScoresOf,
  agentNameForJob,
  cancelAgentEvalJob,
  fetchAgentEvalBundle,
  fetchAgentEvalJob,
  fetchAgentEvalResult,
  joinBundleByTask,
} from '@studio/api/evaluation/agent-evaluations';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { StatusLogsContent } from '@studio/components/evaluation/Jobs/StatusLogsContent';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { AgentEvalScoresPanel } from '@studio/routes/agents/AgentEvaluationsRoute/components/AgentEvalScoresPanel';
import { AgentEvalTaskResultsPanel } from '@studio/routes/agents/AgentEvaluationsRoute/components/AgentEvalTaskResultsPanel';
import {
  getAgentEvaluationsListRoute,
  getAgentsListRoute,
  getFilesetDetailRoute,
} from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ClipboardList, FlaskConical, ScrollText } from 'lucide-react';
import { type FC } from 'react';
import { Link } from 'react-router-dom';

const TERMINAL_STATUSES = new Set([
  'completed',
  'succeeded',
  'success',
  'failed',
  'cancelled',
  'canceled',
  'error',
]);

const isTerminal = (status: string | undefined): boolean =>
  TERMINAL_STATUSES.has((status ?? '').toLowerCase());

export const AgentEvaluationDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { agentEvalJobName: jobName } = useRequiredPathParams([ROUTE_PARAMS.agentEvalJobName]);
  const toast = useToast();
  const queryClient = useQueryClient();

  useBreadcrumbs({
    items: [
      { slotLabel: 'Agents', href: getAgentsListRoute(workspace) },
      { slotLabel: 'Evaluations', href: getAgentEvaluationsListRoute(workspace) },
      { slotLabel: jobName },
    ],
  });

  // Job + status — refetched while the job is non-terminal so the badge stays
  // live without forcing a page reload.
  const { data: job, isLoading: isLoadingJob } = useQuery({
    queryKey: ['agent-eval-job', workspace, jobName] as const,
    queryFn: ({ signal }) => fetchAgentEvalJob(workspace, jobName, signal),
    enabled: !!workspace && !!jobName,
    refetchInterval: (query) => (isTerminal(query.state.data?.status) ? false : 5_000),
  });

  const isJobTerminal = isTerminal(job?.status);

  // Aggregate scores (mean/min/max per metric) from the queryable result record.
  // Only meaningful once the job is terminal. The record is persisted best-effort and
  // may lag the terminal status, so poll while it is still absent and stop once it loads.
  const { data: result, isLoading: isLoadingResult } = useQuery({
    queryKey: ['agent-eval-result', workspace, jobName] as const,
    queryFn: ({ signal }) => fetchAgentEvalResult(workspace, jobName, signal),
    enabled: !!workspace && !!jobName && isJobTerminal,
    refetchInterval: (query) => (query.state.data == null ? 5_000 : false),
  });

  // Per-task detail (agent response + per-task score + diagnostics) from the
  // result bundle referenced by the record. Gated on the result being loaded; polls
  // while the bundle is still absent so late-written artifacts are picked up.
  const { data: bundle, isLoading: isLoadingBundle } = useQuery({
    queryKey: ['agent-eval-bundle', workspace, jobName, result?.bundle_ref] as const,
    queryFn: ({ signal }) => fetchAgentEvalBundle(workspace, result?.bundle_ref, signal),
    enabled: !!workspace && isJobTerminal && !!result?.bundle_ref,
    refetchInterval: (query) => (query.state.data == null ? 5_000 : false),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelAgentEvalJob(workspace, jobName, new AbortController().signal),
    onSuccess: () => {
      toast.success(`Cancellation requested for "${jobName}"`);
      void queryClient.invalidateQueries({
        queryKey: ['agent-eval-job', workspace, jobName] as const,
      });
    },
    onError: (err: Error) => {
      toast.error(`Failed to cancel: ${err.message}`);
    },
  });

  if (isLoadingJob && !job) {
    return (
      <Flex align="center" justify="center" className="h-full w-full">
        <Spinner size="medium" aria-label="Loading evaluation..." />
      </Flex>
    );
  }

  if (!job) {
    return (
      <Stack padding="density-2xl">
        <ErrorMessage
          header="Evaluation not found"
          message={`No evaluation job named "${jobName}" in workspace "${workspace}".`}
        />
      </Stack>
    );
  }

  const statusMessage =
    typeof job.status_details?.message === 'string' ? job.status_details.message : null;
  const errorMessage =
    typeof job.error_details?.message === 'string' ? job.error_details.message : null;
  const scores = aggregateScoresOf(result ?? null);
  const taskDetails = joinBundleByTask(bundle ?? null);

  return (
    <AccessibleTitle title={`Evaluation - ${jobName}`}>
      <Stack className="w-full p-density-2xl min-h-full" gap="density-2xl">
        <PageHeader
          slotHeading={jobName}
          slotDescription="Agent evaluation via nemo-evaluator. Scores aggregate per metric across the evaluated tasks."
          slotActions={
            !isJobTerminal && (
              <Button
                kind="secondary"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
              >
                {cancelMutation.isPending ? 'Cancelling…' : 'Cancel'}
              </Button>
            )
          }
        />

        <Grid cols={{ base: 1, xl: 2 }} gap="density-2xl">
          <Panel
            slotHeading="Job Details"
            slotIcon={<ClipboardList />}
            elevation="high"
            density="compact"
          >
            <Stack gap="density-xl">
              <KVPair label="Name" value={job.name} loading={isLoadingJob} />
              <KVPair
                label="Status"
                value={<StatusBadge status={job.status} />}
                loading={isLoadingJob}
              />
              <KVPair label="Agent" value={agentNameForJob(job) ?? '-'} loading={isLoadingJob} />
              <KVPair
                label="Tasks"
                value={String(job.spec.tasks?.length ?? '-')}
                loading={isLoadingJob}
              />
              {job.description && (
                <KVPair
                  label="Eval Config"
                  value={
                    <Link
                      to={getFilesetDetailRoute(workspace, job.description)}
                      className="text-primary underline"
                    >
                      {job.description}
                    </Link>
                  }
                />
              )}
              <KVPair
                label="Created"
                value={job.created_at ? <RelativeTime datetime={job.created_at} /> : ''}
                loading={isLoadingJob}
              />
              <KVPair
                label="Updated"
                value={job.updated_at ? <RelativeTime datetime={job.updated_at} /> : ''}
                loading={isLoadingJob}
              />
              {(errorMessage ?? statusMessage) && (
                <KVPair
                  label="Response"
                  value={
                    <Text kind="body/regular/sm" color={errorMessage ? 'danger' : 'default'}>
                      {errorMessage ?? statusMessage}
                    </Text>
                  }
                />
              )}
            </Stack>
          </Panel>

          <Panel
            slotHeading="Scores"
            slotIcon={<FlaskConical />}
            elevation="high"
            density="compact"
          >
            {!isJobTerminal && (
              <Block className="text-subtle">
                Scores are computed once the job reaches a terminal state.
              </Block>
            )}
            {isJobTerminal && isLoadingResult && (
              <Flex justify="center" align="center" className="min-h-[120px] w-full">
                <Spinner size="small" aria-label="Loading scores..." />
              </Flex>
            )}
            {isJobTerminal && !isLoadingResult && <AgentEvalScoresPanel scores={scores} />}
          </Panel>
        </Grid>

        {isJobTerminal && isLoadingBundle && (
          <Flex justify="center" align="center" className="min-h-[120px] w-full">
            <Spinner size="small" aria-label="Loading task results..." />
          </Flex>
        )}

        {isJobTerminal && !isLoadingBundle && taskDetails.length > 0 && (
          <AgentEvalTaskResultsPanel tasks={taskDetails} />
        )}

        <AccordionPanel slotHeading="Logs" slotIcon={<ScrollText />}>
          <StatusLogsContent
            workspace={workspace}
            jobName={jobName}
            jobStatus={job.status as PlatformJobStatus}
          />
        </AccordionPanel>
      </Stack>
    </AccessibleTitle>
  );
};
