// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  Badge,
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
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import {
  cancelAgentEvalJob,
  fetchAgentEvalJob,
  fetchEvalConfigFiles,
  fetchEvaluatorOutputs,
  fetchWorkflowOutput,
  isTerminalStatus,
  outputFilesetForJob,
} from '@studio/routes/agents/AgentEvaluationsRoute/api';
import { CompareEvaluationsModal } from '@studio/routes/agents/AgentEvaluationsRoute/components/CompareEvaluationsModal';
import { EvalConfigFilesPanel } from '@studio/routes/agents/AgentEvaluationsRoute/components/EvalConfigFilesPanel';
import { EvalJobLogsPanel } from '@studio/routes/agents/AgentEvaluationsRoute/components/EvalJobLogsPanel';
import { EvaluatorOutputPanel } from '@studio/routes/agents/AgentEvaluationsRoute/components/EvaluatorOutputPanel';
import { WorkflowOutputPanel } from '@studio/routes/agents/AgentEvaluationsRoute/components/WorkflowOutputPanel';
import { formatScore, scoreColor } from '@studio/routes/agents/AgentEvaluationsRoute/evalScores';
import { fetchEvalAverageScores } from '@studio/routes/agents/AgentSuggestionsRoute/api';
import { getAgentEvaluationsListRoute, getAgentsListRoute } from '@studio/routes/utils';
import { useRequiredPathParams } from '@studio/util/hooks/useRequiredPathParams';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ClipboardList, Columns3, FlaskConical, FolderOpen } from 'lucide-react';
import { useState, type FC } from 'react';

const isTerminal = isTerminalStatus;

export const AgentEvaluationDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { agentEvalJobName: jobName } = useRequiredPathParams([ROUTE_PARAMS.agentEvalJobName]);
  const toast = useToast();
  const queryClient = useQueryClient();
  const [compareOpen, setCompareOpen] = useState(false);

  useBreadcrumbs({
    items: [
      { slotLabel: 'Agents', href: getAgentsListRoute(workspace) },
      { slotLabel: 'Evaluations', href: getAgentEvaluationsListRoute(workspace) },
      { slotLabel: jobName },
    ],
  });

  // Job + status — refetched while the job is non-terminal so the badge
  // stays live without forcing a page reload.
  const { data: job, isLoading: isLoadingJob } = useQuery({
    queryKey: ['agent-eval-job', workspace, jobName] as const,
    queryFn: ({ signal }) => fetchAgentEvalJob(workspace, jobName, signal),
    enabled: !!workspace && !!jobName,
    refetchInterval: (query) => (isTerminal(query.state.data?.status) ? false : 5_000),
  });

  const outputFileset = job ? outputFilesetForJob(job) : null;
  const isJobTerminal = isTerminal(job?.status);

  // Evaluator scores from the output fileset — only fetched once the job is
  // terminal; otherwise the fileset doesn't exist yet (or is partial).
  const { data: scores, isLoading: isLoadingScores } = useQuery({
    queryKey: ['agent-eval-scores', workspace, outputFileset] as const,
    queryFn: ({ signal }) =>
      outputFileset
        ? fetchEvalAverageScores(workspace, outputFileset, signal)
        : Promise.resolve([]),
    enabled: !!outputFileset && isJobTerminal,
  });

  // Per-evaluator output (items + judge reasoning) for inline rendering.
  // Same terminal-only gating as scores.
  const { data: evaluatorOutputs, isLoading: isLoadingEvaluatorOutputs } = useQuery({
    queryKey: ['agent-eval-evaluator-outputs', workspace, outputFileset] as const,
    queryFn: ({ signal }) =>
      outputFileset ? fetchEvaluatorOutputs(workspace, outputFileset, signal) : Promise.resolve([]),
    enabled: !!outputFileset && isJobTerminal,
  });

  // workflow_output.json — the agent's responses to the dataset.
  const { data: workflowOutput, isLoading: isLoadingWorkflow } = useQuery({
    queryKey: ['agent-eval-workflow-output', workspace, outputFileset] as const,
    queryFn: ({ signal }) =>
      outputFileset ? fetchWorkflowOutput(workspace, outputFileset, signal) : Promise.resolve(null),
    enabled: !!outputFileset && isJobTerminal,
  });

  // config_original.yml / config_effective.yml / config_metadata.json so
  // the user can audit what actually ran without leaving the page.
  const { data: configFiles, isLoading: isLoadingConfigFiles } = useQuery({
    queryKey: ['agent-eval-config-files', workspace, outputFileset] as const,
    queryFn: ({ signal }) =>
      outputFileset ? fetchEvalConfigFiles(workspace, outputFileset, signal) : Promise.resolve([]),
    enabled: !!outputFileset && isJobTerminal,
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

  const statusError = job.error_details?.message ?? job.status_details?.message;

  return (
    <AccessibleTitle title={`Evaluation - ${jobName}`}>
      <Stack className="w-full p-density-2xl min-h-full" gap="density-2xl">
        <PageHeader
          slotHeading={jobName}
          slotDescription="Evaluation against a deployed agent. Scores aggregate per evaluator from the eval-output fileset."
          slotActions={
            <Flex gap="density-md" align="center">
              {isJobTerminal && job.spec.eval_config && (
                <Button kind="secondary" onClick={() => setCompareOpen(true)}>
                  <Flex gap="density-xs" align="center">
                    <Columns3 size={16} />
                    Compare
                  </Flex>
                </Button>
              )}
              {!isJobTerminal && (
                <Button
                  kind="secondary"
                  onClick={() => cancelMutation.mutate()}
                  disabled={cancelMutation.isPending}
                >
                  {cancelMutation.isPending ? 'Cancelling…' : 'Cancel'}
                </Button>
              )}
            </Flex>
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
              <KVPair label="Agent" value={job.spec.agent ?? '-'} loading={isLoadingJob} />
              <KVPair
                label="Eval Config"
                value={job.spec.eval_config ?? '-'}
                loading={isLoadingJob}
              />
              <KVPair
                label="Eval Config Fileset"
                value={job.spec.eval_config_fileset ?? '-'}
                loading={isLoadingJob}
              />
              <KVPair label="Output Fileset" value={outputFileset ?? '-'} loading={isLoadingJob} />
              <KVPair
                label="Created"
                value={<RelativeTime datetime={job.created_at} />}
                loading={isLoadingJob}
              />
              <KVPair
                label="Updated"
                value={<RelativeTime datetime={job.updated_at} />}
                loading={isLoadingJob}
              />
              {statusError && (
                <KVPair
                  label="Error"
                  value={
                    <Text kind="body/regular/sm" color="danger">
                      {statusError}
                    </Text>
                  }
                />
              )}
            </Stack>
          </Panel>

          <Panel
            slotHeading="Evaluator Scores"
            slotIcon={<FlaskConical />}
            elevation="high"
            density="compact"
          >
            {!isJobTerminal && (
              <Block className="text-subtle">
                Scores are computed once the job reaches a terminal state.
              </Block>
            )}
            {isJobTerminal && isLoadingScores && (
              <Flex justify="center" align="center" className="min-h-[120px] w-full">
                <Spinner size="small" aria-label="Loading scores..." />
              </Flex>
            )}
            {isJobTerminal && !isLoadingScores && (scores?.length ?? 0) === 0 && (
              <Block className="text-subtle">
                No evaluator scores parsed from the output fileset.
              </Block>
            )}
            {isJobTerminal && !isLoadingScores && (scores?.length ?? 0) > 0 && (
              <Stack gap="density-md">
                {scores!.map((s) => (
                  <Flex key={s.evaluator} justify="between" align="center" gap="density-md">
                    <Text kind="body/semibold/md" className="capitalize">
                      {s.evaluator}
                    </Text>
                    <Badge kind="solid" color={scoreColor(s.averageScore)}>
                      {formatScore(s.averageScore)}
                    </Badge>
                  </Flex>
                ))}
              </Stack>
            )}
          </Panel>
        </Grid>

        <EvalJobLogsPanel workspace={workspace} jobName={job.name} jobStatus={job.status} />

        {!isJobTerminal && (
          <Panel
            slotHeading="Eval results"
            slotIcon={<FolderOpen />}
            elevation="high"
            density="compact"
          >
            <Block className="text-subtle">
              Per-item scores, agent responses, and the run config appear once the job completes.
            </Block>
          </Panel>
        )}

        {isJobTerminal &&
          (isLoadingEvaluatorOutputs || isLoadingWorkflow || isLoadingConfigFiles) && (
            <Flex justify="center" align="center" className="min-h-[120px] w-full">
              <Spinner size="small" aria-label="Loading eval results..." />
            </Flex>
          )}

        {isJobTerminal && !isLoadingEvaluatorOutputs && (evaluatorOutputs ?? []).length > 0 && (
          <Stack gap="density-2xl">
            {evaluatorOutputs!.map((output) => (
              <EvaluatorOutputPanel key={output.evaluator} output={output} />
            ))}
          </Stack>
        )}

        {isJobTerminal && !isLoadingWorkflow && workflowOutput && workflowOutput.length > 0 && (
          <WorkflowOutputPanel items={workflowOutput} evaluatorOutputs={evaluatorOutputs ?? []} />
        )}

        {isJobTerminal && !isLoadingConfigFiles && (configFiles ?? []).length > 0 && (
          <EvalConfigFilesPanel files={configFiles!} />
        )}
      </Stack>
      {job.spec.eval_config && (
        <CompareEvaluationsModal
          open={compareOpen}
          onClose={() => setCompareOpen(false)}
          workspace={workspace}
          evalConfig={job.spec.eval_config}
          baseJob={job}
        />
      )}
    </AccessibleTitle>
  );
};
