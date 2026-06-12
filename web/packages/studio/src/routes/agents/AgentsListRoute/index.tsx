// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getAgentsListAgentsQueryKey, useAgentsCreateAgent } from '@nemo/sdk/generated/agents/api';
import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import { useModelsListModels } from '@nemo/sdk/generated/platform/api';
import { PageHeader, Stack } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { AgentsTable, type AgentTableRow } from '@studio/components/dataViews/AgentsDataView';
import {
  AgentPanel,
  type AgentPanelTab,
} from '@studio/components/sidePanels/AgentPanels/AgentPanel';
import {
  hasShownExampleAgentIntro,
  markAgentWalkthroughPending,
  markExampleAgentIntroShown,
} from '@studio/components/sidePanels/AgentPanels/AgentPanel/walkthroughStorage';
import { DEFAULT_LARGE_PAGE_SIZE } from '@studio/constants/constants';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { CreateDeploymentModal } from '@studio/routes/agents/AgentDeploymentsListRoute/CreateDeploymentModal';
import { getAgentDetailRoute, getAgentsListRoute } from '@studio/routes/utils';
import { pickDefaultModelName } from '@studio/util/buildSuggestedModelOptions';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

const TAB_SEARCH_PARAM = 'tab';

const EXAMPLE_AGENT_DESCRIPTION = 'A ReAct agent with a calculator and datetime tool.';

const EXAMPLE_AGENT_NAME_PREFIX = 'calculator-demo-agent';

const buildExampleAgentName = (): string =>
  `${EXAMPLE_AGENT_NAME_PREFIX}-${Math.random().toString(36).slice(2, 8)}`;

const isExampleAgentName = (name: string): boolean => name.startsWith(EXAMPLE_AGENT_NAME_PREFIX);

// model_name is concrete: the service doesn't resolve ${NEMO_DEFAULT_MODEL} (only the CLI does).
const buildExampleAgentConfig = (modelName: string): Record<string, unknown> => ({
  function_groups: {
    calculator: { _type: 'calculator' },
  },
  functions: {
    current_datetime: { _type: 'current_datetime' },
  },
  llms: {
    llm: {
      _type: 'openai',
      api_key: 'not-used', // platform overrides at deploy time
      model_name: modelName,
      temperature: 0,
    },
  },
  workflow: {
    _type: 'react_agent',
    tool_names: ['calculator', 'current_datetime'],
    llm_name: 'llm',
    verbose: false,
    parse_agent_response_max_retries: 3,
    use_native_tool_calling: true,
  },
  general: {
    telemetry: {
      tracing: {
        nemo_trace: { _type: 'nemo_files', batch_size: 128 },
      },
    },
  },
});

export const AgentsListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [createDeploymentAgent, setCreateDeploymentAgent] = useState<string | null>(null);
  const { [ROUTE_PARAMS.agentName]: agentNameParam } = useParams<{ agentName?: string }>();
  const tabFromUrl: AgentPanelTab =
    (searchParams.get(TAB_SEARCH_PARAM) as AgentPanelTab) || 'agent-details';

  useBreadcrumbs({
    items: [{ slotLabel: 'Agents' }],
  });

  const { data: modelsPage, isLoading: isLoadingModels } = useModelsListModels(
    workspace,
    { page_size: DEFAULT_LARGE_PAGE_SIZE },
    { query: { enabled: !!workspace } }
  );

  const [loadedAgents, setLoadedAgents] = useState<Agent[]>([]);

  const { mutateAsync: createAgent, isPending } = useAgentsCreateAgent({
    mutation: {
      onSuccess: (agent) => {
        toast.success(`Agent "${agent.name}" created`);
        // Refresh the table immediately instead of waiting for its poll interval.
        void queryClient.invalidateQueries({ queryKey: getAgentsListAgentsQueryKey(workspace) });
        const priorExampleAgentExists = loadedAgents.some(
          (existing) =>
            !!existing.name && existing.name !== agent.name && isExampleAgentName(existing.name)
        );
        if (agent.name && !hasShownExampleAgentIntro() && !priorExampleAgentExists) {
          markExampleAgentIntroShown();
          markAgentWalkthroughPending(agent.name);
          navigate(getAgentDetailRoute(workspace, agent.name));
        } else {
          navigate(getAgentsListRoute(workspace));
        }
      },
      onError: (err) => {
        toast.error(getErrorMessage(err as Error, 'Failed to create example agent'));
      },
    },
  });

  const [pendingCreate, setPendingCreate] = useState(false);

  const doCreate = useCallback(() => {
    const modelName = pickDefaultModelName(modelsPage?.data ?? []);
    if (!modelName) {
      toast.error('No usable chat model in this workspace. Add a model before creating an agent.');
      return;
    }
    void createAgent({
      workspace,
      data: {
        name: buildExampleAgentName(),
        description: EXAMPLE_AGENT_DESCRIPTION,
        config: buildExampleAgentConfig(modelName),
      },
    }).catch(() => {});
  }, [modelsPage, workspace, createAgent, toast]);

  // If models finished loading while a create was queued, execute it now.
  useEffect(() => {
    if (!pendingCreate || isLoadingModels) return;
    setPendingCreate(false);
    doCreate();
  }, [pendingCreate, isLoadingModels, doCreate]);

  const handleCreateExample = () => {
    if (isLoadingModels) {
      setPendingCreate(true);
      return;
    }
    doCreate();
  };

  const handleOpenPanel = (agent: AgentTableRow) => {
    navigate(`${getAgentDetailRoute(workspace, agent.name)}?${TAB_SEARCH_PARAM}=agent-details`, {
      replace: true,
    });
  };

  const handleClosePanel = () => {
    navigate(getAgentsListRoute(workspace), { replace: true });
  };

  return (
    <AccessibleTitle title={`Agents for ${workspace}`}>
      <Stack className="h-full" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Agents"
          slotDescription="View and manage AI agents and their deployments."
          slotActions={
            <LoadingButton
              color="brand"
              loading={isPending || (pendingCreate && isLoadingModels)}
              onClick={handleCreateExample}
            >
              Create Example Agent
            </LoadingButton>
          }
        />
        <AgentsTable
          onAgentRowClick={handleOpenPanel}
          onCreateDeployment={(agentName) => setCreateDeploymentAgent(agentName)}
          onAgentsLoaded={setLoadedAgents}
        />
      </Stack>
      <CreateDeploymentModal
        open={createDeploymentAgent !== null}
        agent={createDeploymentAgent || undefined}
        onClose={() => setCreateDeploymentAgent(null)}
        workspace={workspace}
      />
      <AgentPanel
        open={!!agentNameParam}
        agentName={agentNameParam}
        workspace={workspace}
        defaultTab={tabFromUrl}
        onTabChange={(tab) =>
          setSearchParams(
            (prev) => {
              prev.set(TAB_SEARCH_PARAM, tab);
              return prev;
            },
            { replace: true }
          )
        }
        onOpenChange={(open) => {
          if (!open) handleClosePanel();
        }}
      />
    </AccessibleTitle>
  );
};
