// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { JOB_POLLING_INTERVAL_LONG, JOB_POLLING_INTERVAL_MS } from '@nemo/common/src/constants';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  getAgentsListDeploymentsQueryKey,
  useAgentsDeleteDeployment,
  useAgentsGetAgent,
  useAgentsListDeployments,
} from '@nemo/sdk/generated/agents/api';
import { useListEvaluations, useListExperiments } from '@nemo/sdk/generated/platform/api';
import type { EvaluationResponse } from '@nemo/sdk/generated/platform/schema';
import { fetchEvaluatorJobs } from '@studio/api/evaluation/evaluator-jobs';
import { type EvalJobRow, targetNameForEvalJob, toEvalJobRow } from '@studio/api/evaluation/utils';
import { RECENT_EVAL_LIMIT } from '@studio/routes/agents/AgentDetailRoute/constants';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';

/** Backend caps page_size at 100. Enough to name the experiments behind a panel's worth of rows. */
const EXPERIMENT_PAGE_SIZE = 100;

/** Statuses that will not change again, so polling can stop. */
const TERMINAL_JOB_STATUSES = new Set(['completed', 'error', 'cancelled']);

/** A published evaluation plus the experiment it belongs to — the name its detail route is nested
 *  under, and the description the overview cards label it with. Both are null when the experiment
 *  falls outside the fetched page. */
export type AgentEvaluationRow = EvaluationResponse & {
  experimentName: string | null;
  experimentDescription: string | null;
};

interface UseAgentPanelParams {
  workspace: string;
  agentName?: string;
  selectedDeploymentName?: string;
}

export const useAgentDetails = ({
  workspace,
  agentName,
  selectedDeploymentName,
}: UseAgentPanelParams) => {
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data: agent } = useAgentsGetAgent(workspace, agentName ?? '', {
    query: { enabled: !!agentName && !!workspace },
  });

  const { data: deploymentsResponse, isLoading: isDeploymentsLoading } = useAgentsListDeployments(
    workspace,
    undefined,
    {
      query: {
        enabled: !!agentName,
        // Poll quickly while any deployment is mid-transition (pending/starting/deleting)
        // so the panel reflects controller-side progress; fall back to the long interval
        // otherwise to match the agents table.
        refetchInterval: (query) => {
          const deployments = query.state.data?.data ?? [];
          const transitional = deployments.some(
            (d) =>
              d.agent === agentName &&
              (d.status === 'pending' || d.status === 'starting' || d.status === 'deleting')
          );
          return transitional ? JOB_POLLING_INTERVAL_MS : JOB_POLLING_INTERVAL_LONG;
        },
      },
    }
  );

  const deploymentsData = deploymentsResponse?.data;

  const { data: agentEvalsResponse, isPending: isAgentEvalsPending } = useListEvaluations(
    workspace,
    {
      filter: { agent_name: agentName ?? '' },
      page_size: RECENT_EVAL_LIMIT,
      sort: '-created_at',
    },
    { query: { enabled: !!agentName && !!workspace } }
  );

  const { data: agentJobsData } = useQuery({
    queryKey: ['evaluator-jobs', workspace, 'agent-panel', agentName] as const,
    queryFn: ({ signal }) =>
      fetchEvaluatorJobs(workspace, signal, (all) => {
        const matched = all.filter((job) => targetNameForEvalJob(job) === agentName).length;
        return matched >= RECENT_EVAL_LIMIT;
      }),
    enabled: !!agentName && !!workspace,
    refetchInterval: (query) => {
      const rows = (query.state.data ?? []).map(toEvalJobRow);
      const live = rows.some((row) => !TERMINAL_JOB_STATUSES.has(row.status ?? ''));
      return live ? JOB_POLLING_INTERVAL_MS : false;
    },
  });

  const deleteDeploymentMutation = useAgentsDeleteDeployment({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({
          queryKey: getAgentsListDeploymentsQueryKey(workspace),
        });
      },
      onError: (error) => {
        toast.error(error.message);
      },
    },
  });

  const agentDeployments = useMemo(
    () => (deploymentsData ?? []).filter((d) => d.agent === agentName),
    [deploymentsData, agentName]
  );

  const { data: experimentsResponse } = useListExperiments(
    workspace,
    { page_size: EXPERIMENT_PAGE_SIZE, sort: '-created_at' },
    { query: { enabled: !!agentName && !!workspace } }
  );

  const agentEvals: AgentEvaluationRow[] = useMemo(() => {
    if (!agentName) return [];
    const byId = new Map(
      (experimentsResponse?.data ?? []).map((experiment) => [experiment.id, experiment])
    );
    return (agentEvalsResponse?.data ?? []).map((evaluation) => {
      const experiment = byId.get(evaluation.experiment_ids[0] ?? '');
      return {
        ...evaluation,
        experimentName: experiment?.name ?? null,
        experimentDescription: experiment?.description ?? null,
      };
    });
  }, [agentEvalsResponse, experimentsResponse, agentName]);

  const agentJobs: EvalJobRow[] = useMemo(() => {
    if (!agentName) return [];
    return (agentJobsData ?? [])
      .filter((job) => targetNameForEvalJob(job) === agentName)
      .slice(0, RECENT_EVAL_LIMIT)
      .map(toEvalJobRow);
  }, [agentJobsData, agentName]);

  const healthyDeployments = useMemo(
    () => agentDeployments.filter((d) => d.status === 'running'),
    [agentDeployments]
  );

  const isDeploying = useMemo(
    () => agentDeployments.some((d) => d.status === 'pending' || d.status === 'starting'),
    [agentDeployments]
  );

  const chatDeployment = useMemo(() => {
    if (selectedDeploymentName) {
      return healthyDeployments.find((d) => d.name === selectedDeploymentName);
    }
    return healthyDeployments[0];
  }, [healthyDeployments, selectedDeploymentName]);

  return {
    isDeploymentsLoading,
    agent,
    agentDeployments,
    agentEvals,
    isAgentEvalsPending,
    agentJobs,
    healthyDeployments,
    isDeploying,
    chatDeployment,
    deleteDeploymentMutation,
  };
};
