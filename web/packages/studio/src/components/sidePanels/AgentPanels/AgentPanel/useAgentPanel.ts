// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { JOB_POLLING_INTERVAL_LONG, JOB_POLLING_INTERVAL_MS } from '@nemo/common/src/constants';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  getAgentsListDeploymentsQueryKey,
  useAgentsDeleteDeployment,
  useAgentsListAgents,
  useAgentsListDeployments,
} from '@nemo/sdk/generated/agents/api';
import { RECENT_EVAL_LIMIT } from '@studio/components/sidePanels/AgentPanels/AgentPanel/constants';
import { fetchAgentEvalJobs } from '@studio/routes/agents/AgentEvaluationsRoute/api';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';

interface UseAgentPanelParams {
  workspace: string;
  agentName?: string;
  selectedDeploymentName?: string;
}

export const useAgentPanel = ({
  workspace,
  agentName,
  selectedDeploymentName,
}: UseAgentPanelParams) => {
  const queryClient = useQueryClient();
  const toast = useToast();

  const { data: agentsResponse } = useAgentsListAgents(workspace, undefined, {
    query: { enabled: !!agentName },
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

  const agentsData = agentsResponse?.data;
  const deploymentsData = deploymentsResponse?.data;

  // Recent evaluations targeting this agent. The platform's job filter API
  // doesn't expose ``spec.agent`` as a top-level filter, so we fetch the
  // workspace's eval jobs and filter client-side. Capped at the most recent
  // N to keep the panel scannable; the full list is on the evaluations route.
  const { data: agentEvalsData } = useQuery({
    queryKey: ['agent-eval-jobs', workspace, 'panel', agentName] as const,
    queryFn: ({ signal }) => fetchAgentEvalJobs(workspace, signal),
    enabled: !!agentName && !!workspace,
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

  const agent = agentName ? (agentsData ?? []).find((a) => a.name === agentName) : undefined;
  const agentDeployments = useMemo(
    () => (deploymentsData ?? []).filter((d) => d.agent === agentName),
    [deploymentsData, agentName]
  );

  const agentEvals = useMemo(() => {
    if (!agentName) return [];
    const all = agentEvalsData ?? [];
    // Match either the bare agent name or a workspace-prefixed ref.
    const matches = all.filter((job) => {
      const a = job.spec.agent;
      if (typeof a !== 'string') return false;
      const bare = a.includes('/') ? a.split('/').pop() : a;
      return a === agentName || bare === agentName;
    });
    return matches.slice(0, RECENT_EVAL_LIMIT);
  }, [agentEvalsData, agentName]);

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
    healthyDeployments,
    isDeploying,
    chatDeployment,
    deleteDeploymentMutation,
  };
};
