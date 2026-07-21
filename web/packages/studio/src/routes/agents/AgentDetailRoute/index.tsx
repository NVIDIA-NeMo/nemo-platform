// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import type { AgentDeployment } from '@nemo/sdk/generated/agents/schema/AgentDeployment';
import {
  Button,
  Flex,
  PageHeader,
  Stack,
  TabsContent,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { getAgentModelNames } from '@studio/components/dataViews/AgentsDataView/utils';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { ChatPlaygroundContent } from '@studio/components/sidePanels/AgentPanels/AgentPanel/ChatPlaygroundContent';
import { DeploymentLogsView } from '@studio/components/sidePanels/AgentPanels/AgentPanel/DeploymentLogsView';
import { useAgentPanel } from '@studio/components/sidePanels/AgentPanels/AgentPanel/useAgentPanel';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { CreateDeploymentModal } from '@studio/routes/agents/AgentDeploymentsListRoute/CreateDeploymentModal';
import { DeploymentsTab } from '@studio/routes/agents/AgentDetailRoute/DeploymentsTab';
import { EvaluationsTab } from '@studio/routes/agents/AgentDetailRoute/EvaluationsTab';
import { SubmitEvaluationModal } from '@studio/routes/agents/AgentEvaluationsRoute/components/SubmitEvaluationModal';
import { getAgentMonitorRoute, getAgentsListRoute } from '@studio/routes/utils';
import { Activity, ClipboardCheck, Dot, Rocket } from 'lucide-react';
import { type FC, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

const TAB_SEARCH_PARAM = 'tab';
const DETAIL_TABS = ['deployments', 'logs', 'chat', 'evaluations'] as const;
const DEFAULT_TAB = 'deployments';

type AgentDetailTab = (typeof DETAIL_TABS)[number];

const isAgentDetailTab = (value: string | null): value is AgentDetailTab =>
  !!value && DETAIL_TABS.includes(value as AgentDetailTab);

export const AgentDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const { [ROUTE_PARAMS.agentName]: agentName } = useParams<{ agentName: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedDeploymentName, setSelectedDeploymentName] = useState<string | undefined>();
  const [logsDeploymentName, setLogsDeploymentName] = useState<string | undefined>();
  const [createDeploymentOpen, setCreateDeploymentOpen] = useState(false);
  const [submitEvalOpen, setSubmitEvalOpen] = useState(false);
  const [deleteDeploymentTarget, setDeleteDeploymentTarget] = useState<AgentDeployment | null>(
    null
  );
  const chatAreaRef = useRef<HTMLDivElement>(null);
  const tabFromUrl = searchParams.get(TAB_SEARCH_PARAM);
  const selectedTab: AgentDetailTab = isAgentDetailTab(tabFromUrl) ? tabFromUrl : DEFAULT_TAB;

  const {
    agent,
    agentDeployments,
    agentEvals,
    chatDeployment,
    deleteDeploymentMutation,
    healthyDeployments,
    isDeploying,
    isDeploymentsLoading,
  } = useAgentPanel({ workspace, agentName, selectedDeploymentName });

  useBreadcrumbs({
    items: [
      { slotLabel: 'Agents', href: getAgentsListRoute(workspace) },
      { slotLabel: agentName ?? 'Agent details' },
    ],
  });

  const setSelectedTab = (tab: AgentDetailTab) => {
    setSearchParams({ [TAB_SEARCH_PARAM]: tab }, { replace: true });
  };

  const switchToChat = (deployment: AgentDeployment) => {
    setSelectedDeploymentName(deployment.name);
    setSelectedTab('chat');
  };

  const viewLogs = (deployment: AgentDeployment) => {
    setLogsDeploymentName(deployment.name);
    setSelectedTab('logs');
  };

  const modelNames = getAgentModelNames(agent?.config);

  const status = healthyDeployments.length > 0 ? 'running' : agentDeployments[0]?.status;
  const statusPillLabel =
    healthyDeployments.length > 0
      ? 'Healthy'
      : status === 'pending' || status === 'starting'
        ? 'Deploying'
        : status === 'deleting'
          ? 'Deleting'
          : status === 'failed'
            ? 'Failed'
            : agentDeployments.length === 0
              ? 'No deployments'
              : (status ?? 'Unknown');

  return (
    <AccessibleTitle title={`${agentName ?? 'Agent'} details for ${workspace}`}>
      <Stack className="h-full min-h-0" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="shrink-0 p-0"
          slotHeading={
            <Stack gap="1">
              <Flex align="baseline" gap="3">
                <Text kind="title/md">{agent?.name ?? agentName ?? 'Agent details'}</Text>
                <StatusBadge status={status} label={statusPillLabel} />
              </Flex>
              <Flex align="center" gap="1">
                <Text kind="body/regular/sm" className="text-secondary">
                  {modelNames.join(', ')}
                </Text>
                {agent?.description && (
                  <>
                    <Dot className="size-2" aria-hidden />
                    <Text kind="body/regular/sm" className="text-secondary">
                      {agent.description}
                    </Text>
                  </>
                )}
              </Flex>
            </Stack>
          }
          slotActions={
            <Flex gap="2" wrap="wrap" justify="end">
              <Button kind="secondary" onClick={() => navigate(getAgentMonitorRoute(workspace))}>
                <Activity className="size-4" aria-hidden />
                Open traces
              </Button>
              <Button
                kind="secondary"
                onClick={() => setSubmitEvalOpen(true)}
                disabled={!agentName}
              >
                <ClipboardCheck className="size-4" aria-hidden />
                Run evaluation
              </Button>
              <Button
                color="brand"
                onClick={() => setCreateDeploymentOpen(true)}
                disabled={!agentName || isDeploying}
              >
                <Rocket className="size-4" aria-hidden />
                {isDeploying ? 'Deploying...' : 'Deploy'}
              </Button>
            </Flex>
          }
        ></PageHeader>

        <TabsRoot
          className="flex min-h-0 flex-1 flex-col"
          value={selectedTab}
          onValueChange={(value) => {
            if (isAgentDetailTab(value)) setSelectedTab(value);
          }}
        >
          <TabsList className="shrink-0">
            <TabsTrigger value="deployments">Deployments</TabsTrigger>
            <TabsTrigger value="logs">Logs</TabsTrigger>
            <TabsTrigger value="chat">Chat</TabsTrigger>
            <TabsTrigger value="evaluations">Evaluations</TabsTrigger>
          </TabsList>

          <TabsContent className="min-h-0 flex-1 overflow-auto p-0 pt-6" value="evaluations">
            <EvaluationsTab
              workspace={workspace}
              evals={agentEvals}
              onRunEvaluation={() => setSubmitEvalOpen(true)}
            />
          </TabsContent>

          <TabsContent className="min-h-0 flex-1 overflow-auto p-0 pt-6" value="deployments">
            <DeploymentsTab
              agentName={agentName}
              deployments={agentDeployments}
              isDeploymentsLoading={isDeploymentsLoading}
              isDeploying={isDeploying}
              onDeploy={() => setCreateDeploymentOpen(true)}
              onChat={switchToChat}
              onDelete={setDeleteDeploymentTarget}
              onViewLogs={viewLogs}
            />
          </TabsContent>

          <TabsContent className="min-h-0 flex-1 overflow-auto p-0 pt-6" value="logs">
            <DeploymentLogsView
              workspace={workspace}
              deployments={agentDeployments}
              selectedDeploymentName={logsDeploymentName}
              onSelectDeployment={setLogsDeploymentName}
            />
          </TabsContent>

          <TabsContent className="min-h-0 flex-1 overflow-hidden p-0 pt-6" value="chat">
            <div className="mx-auto flex h-full w-full max-w-4xl flex-col">
              <ChatPlaygroundContent
                workspace={workspace}
                agentName={agentName}
                chatDeployment={chatDeployment}
                healthyDeployments={healthyDeployments}
                isDeploymentsLoading={isDeploymentsLoading}
                isDeploying={isDeploying}
                chatAreaRef={chatAreaRef}
                onSelectDeployment={setSelectedDeploymentName}
                onDeploy={() => setCreateDeploymentOpen(true)}
              />
            </div>
          </TabsContent>
        </TabsRoot>
      </Stack>
      <SubmitEvaluationModal
        open={submitEvalOpen}
        onClose={() => setSubmitEvalOpen(false)}
        workspace={workspace}
        agent={agentName}
      />
      {createDeploymentOpen && (
        <CreateDeploymentModal
          open
          agent={agentName}
          workspace={workspace}
          onClose={() => setCreateDeploymentOpen(false)}
        />
      )}
      {deleteDeploymentTarget && (
        <DeleteConfirmationModal
          open
          title="Delete Deployment"
          successText="Successfully queued deployment for deletion."
          onDelete={async () => {
            try {
              if (!deleteDeploymentTarget.name) return false;
              await deleteDeploymentMutation.mutateAsync({
                workspace,
                name: deleteDeploymentTarget.name,
              });
              return true;
            } catch {
              return false;
            }
          }}
          onClose={() => setDeleteDeploymentTarget(null)}
          simpleConfirm
        />
      )}
    </AccessibleTitle>
  );
};
