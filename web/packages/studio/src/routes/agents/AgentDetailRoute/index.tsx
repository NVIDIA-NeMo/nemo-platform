// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AccessibleTitle } from '@nemo/common/src/components/AccessibleTitle';
import { DeleteConfirmationModal } from '@nemo/common/src/components/DeleteConfirmationModal';
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
import { getAgentModelNames } from '@studio/components/dataViews/AgentsDataView/utils';
import { SubmitEvaluationModal } from '@studio/components/evaluation/SubmitEvaluationModal';
import { MONITOR_ENABLED } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { CreateDeploymentModal } from '@studio/routes/agents/AgentDeploymentsListRoute/CreateDeploymentModal';
import { ChatPlaygroundContent } from '@studio/routes/agents/AgentDetailRoute/ChatPlaygroundContent';
import { DeploymentLogsView } from '@studio/routes/agents/AgentDetailRoute/DeploymentLogsView';
import { DeploymentsTab } from '@studio/routes/agents/AgentDetailRoute/DeploymentsTab';
import { DetailsTab } from '@studio/routes/agents/AgentDetailRoute/DetailsTab';
import { EvaluationsTab } from '@studio/routes/agents/AgentDetailRoute/EvaluationsTab';
import { useAgentDetails } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';
import { deriveWalkthroughStep } from '@studio/routes/agents/AgentDetailRoute/walkthrough';
import { WalkthroughCoachmarks } from '@studio/routes/agents/AgentDetailRoute/WalkthroughCoachmarks';
import {
  clearAgentWalkthroughPending,
  isAgentWalkthroughPending,
} from '@studio/routes/agents/AgentDetailRoute/walkthroughStorage';
import { getAgentMonitorRoute, getAgentsListRoute } from '@studio/routes/utils';
import { Activity, ClipboardCheck, Dot, Rocket } from 'lucide-react';
import { type FC, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router';

const TAB_SEARCH_PARAM = 'tab';
const DETAIL_TABS = ['deployments', 'logs', 'chat', 'evaluations', 'details'] as const;
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
  const deployButtonRef = useRef<HTMLDivElement>(null);
  const tabsRef = useRef<HTMLDivElement>(null);
  const [walkthroughActive, setWalkthroughActive] = useState(false);
  const [walkthroughDismissed, setWalkthroughDismissed] = useState(false);
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
  } = useAgentDetails({ workspace, agentName, selectedDeploymentName });

  useBreadcrumbs({
    items: [
      { slotLabel: 'Agents', href: getAgentsListRoute(workspace) },
      { slotLabel: agentName ?? 'Agent details' },
    ],
  });

  useEffect(() => {
    setWalkthroughDismissed(false);
    setWalkthroughActive(!!agentName && isAgentWalkthroughPending(agentName));
  }, [agentName]);

  const walkthroughStep = deriveWalkthroughStep({
    active: walkthroughActive,
    dismissed: walkthroughDismissed,
    createDeploymentOpen,
    selectedTab,
    hasDeployment: agentDeployments.length > 0,
    hasHealthyDeployment: healthyDeployments.length > 0,
  });

  const endWalkthrough = () => {
    setWalkthroughDismissed(true);
    if (agentName) clearAgentWalkthroughPending(agentName);
  };

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
              {MONITOR_ENABLED && (
                <Button kind="secondary" onClick={() => navigate(getAgentMonitorRoute(workspace))}>
                  <Activity className="size-4" aria-hidden />
                  Open traces
                </Button>
              )}
              <Button
                kind="secondary"
                onClick={() => setSubmitEvalOpen(true)}
                disabled={!agentName}
              >
                <ClipboardCheck className="size-4" aria-hidden />
                Run evaluation
              </Button>
              <div ref={deployButtonRef}>
                <Button
                  color="brand"
                  onClick={() => setCreateDeploymentOpen(true)}
                  disabled={!agentName || isDeploying}
                >
                  <Rocket className="size-4" aria-hidden />
                  {isDeploying ? 'Deploying...' : 'Deploy'}
                </Button>
              </div>
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
          <TabsList className="shrink-0" ref={tabsRef}>
            <TabsTrigger value="deployments">Deployments</TabsTrigger>
            <TabsTrigger value="logs">Logs</TabsTrigger>
            <TabsTrigger value="chat">Chat</TabsTrigger>
            <TabsTrigger value="evaluations">Evaluations</TabsTrigger>
            <TabsTrigger value="details">Details</TabsTrigger>
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

          <TabsContent className="min-h-0 flex-1 overflow-auto p-0 pt-6" value="details">
            <DetailsTab workspace={workspace} agentName={agentName} agent={agent} />
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
      <WalkthroughCoachmarks
        walkthroughStep={walkthroughStep}
        deployButtonRef={deployButtonRef}
        tabsRef={tabsRef}
        chatAreaRef={chatAreaRef}
        onDismiss={endWalkthrough}
      />
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
