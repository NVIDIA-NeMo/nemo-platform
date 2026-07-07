// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import { Button, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { AgentsTable, type AgentTableRow } from '@studio/components/dataViews/AgentsDataView';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { usePluginInstalled, usePluginsLoaded } from '@studio/plugins/PluginContext';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { CreateDeploymentModal } from '@studio/routes/agents/AgentDeploymentsListRoute/CreateDeploymentModal';
import { CloneAgentModal } from '@studio/routes/agents/AgentsListRoute/CloneAgentModal';
import { CreateExampleAgentModal } from '@studio/routes/agents/AgentsListRoute/CreateExampleAgentModal';
import { getAgentDetailRoute } from '@studio/routes/utils';
import { CircleAlert } from 'lucide-react';
import { type FC, useState } from 'react';
import { useNavigate } from 'react-router-dom';

export const AgentsListRoute: FC = () => {
  const pluginsLoaded = usePluginsLoaded();
  const agentsInstalled = usePluginInstalled('agents');
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const [createDeploymentAgent, setCreateDeploymentAgent] = useState<string | null>(null);
  const [isCreateExampleOpen, setCreateExampleOpen] = useState(false);
  const [cloneSource, setCloneSource] = useState<AgentTableRow | null>(null);
  const [loadedAgents, setLoadedAgents] = useState<Agent[]>([]);

  useBreadcrumbs({
    items: [{ slotLabel: 'Agents' }],
  });

  const handleOpenDetails = (agent: AgentTableRow) =>
    navigate(getAgentDetailRoute(workspace, agent.name));

  if (pluginsLoaded && !agentsInstalled) {
    return (
      <Stack className="h-full justify-center mx-auto max-w-[640px]" gap="density-md">
        <CircleAlert className="size-16 stroke-2" color="var(--text-color-feedback-danger)" />
        <Text kind="display/xl">Plugin Not Enabled</Text>
        <Text kind="title/lg">The Agents plugin is not installed.</Text>
        <Text lineHeight="150">
          To use this page, the <strong>agents</strong> plugin must be registered with the platform.
          Ask your administrator to install and enable the agents plugin.
        </Text>
      </Stack>
    );
  }

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
          onAgentRowClick={handleOpenDetails}
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
    </AccessibleTitle>
  );
};
