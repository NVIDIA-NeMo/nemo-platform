// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import { Button, PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { AgentsTable, type AgentTableRow } from '@studio/components/dataViews/AgentsDataView';
import {
  AgentPanel,
  type AgentPanelTab,
} from '@studio/components/sidePanels/AgentPanels/AgentPanel';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { CreateDeploymentModal } from '@studio/routes/agents/AgentDeploymentsListRoute/CreateDeploymentModal';
import { CloneAgentModal } from '@studio/routes/agents/AgentsListRoute/CloneAgentModal';
import { CreateExampleAgentModal } from '@studio/routes/agents/AgentsListRoute/CreateExampleAgentModal';
import { getAgentDetailRoute, getAgentsListRoute } from '@studio/routes/utils';
import { type FC, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

const TAB_SEARCH_PARAM = 'tab';

export const AgentsListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [createDeploymentAgent, setCreateDeploymentAgent] = useState<string | null>(null);
  const [isCreateExampleOpen, setCreateExampleOpen] = useState(false);
  const [cloneSource, setCloneSource] = useState<AgentTableRow | null>(null);
  const [loadedAgents, setLoadedAgents] = useState<Agent[]>([]);
  const { [ROUTE_PARAMS.agentName]: agentNameParam } = useParams<{ agentName?: string }>();
  const tabFromUrl: AgentPanelTab =
    (searchParams.get(TAB_SEARCH_PARAM) as AgentPanelTab) || 'agent-details';

  useBreadcrumbs({
    items: [{ slotLabel: 'Agents' }],
  });

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
            <Button color="brand" onClick={() => setCreateExampleOpen(true)}>
              Create Example Agent
            </Button>
          }
        />
        <AgentsTable
          onAgentRowClick={handleOpenPanel}
          onCreateDeployment={(agentName) => setCreateDeploymentAgent(agentName)}
          onCloneAgent={setCloneSource}
          onAgentsLoaded={setLoadedAgents}
        />
      </Stack>
      <CreateExampleAgentModal
        open={isCreateExampleOpen}
        onClose={() => setCreateExampleOpen(false)}
        workspace={workspace}
        existingAgents={loadedAgents}
      />
      <CloneAgentModal
        open={cloneSource !== null}
        onClose={() => setCloneSource(null)}
        workspace={workspace}
        sourceAgent={cloneSource}
      />
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
