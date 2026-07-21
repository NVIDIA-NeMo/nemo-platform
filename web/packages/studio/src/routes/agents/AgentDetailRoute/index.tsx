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
  Tooltip,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { ChatPlaygroundContent } from '@studio/components/sidePanels/AgentPanels/AgentPanel/ChatPlaygroundContent';
import { useAgentPanel } from '@studio/components/sidePanels/AgentPanels/AgentPanel/useAgentPanel';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { CreateDeploymentModal } from '@studio/routes/agents/AgentDeploymentsListRoute/CreateDeploymentModal';
import { ConfigurationTab } from '@studio/routes/agents/AgentDetailRoute/ConfigurationTab';
import { DeploymentsTab } from '@studio/routes/agents/AgentDetailRoute/DeploymentsTab';
import { EvaluationsTab } from '@studio/routes/agents/AgentDetailRoute/EvaluationsTab';
import { TabPlaceholder } from '@studio/routes/agents/AgentDetailRoute/TabPlaceholder';
import { SubmitEvaluationModal } from '@studio/routes/agents/AgentEvaluationsRoute/components/SubmitEvaluationModal';
import { getAgentMonitorRoute, getAgentsListRoute } from '@studio/routes/utils';
import {
  Activity,
  ClipboardCheck,
  LayoutDashboard,
  Rocket,
  Sparkles,
  Waypoints,
} from 'lucide-react';
import { type FC, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

const TAB_SEARCH_PARAM = 'tab';
const DETAIL_TABS = [
  'overview',
  'traces',
  'evaluations',
  'improvements',
  'deployments',
  'configuration',
  'chat',
] as const;

type AgentDetailTab = (typeof DETAIL_TABS)[number];

const isAgentDetailTab = (value: string | null): value is AgentDetailTab =>
  !!value && DETAIL_TABS.includes(value as AgentDetailTab);

export const AgentDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const { [ROUTE_PARAMS.agentName]: agentName } = useParams<{ agentName: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedDeploymentName, setSelectedDeploymentName] = useState<string | undefined>();
  const [createDeploymentOpen, setCreateDeploymentOpen] = useState(false);
  const [submitEvalOpen, setSubmitEvalOpen] = useState(false);
  const [deleteDeploymentTarget, setDeleteDeploymentTarget] = useState<AgentDeployment | null>(
    null
  );
  const chatAreaRef = useRef<HTMLDivElement>(null);
  const tabFromUrl = searchParams.get(TAB_SEARCH_PARAM);
  const selectedTab: AgentDetailTab = isAgentDetailTab(tabFromUrl) ? tabFromUrl : 'overview';

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
  const totalDeployments = agentDeployments.length;
  const statusDetail =
    totalDeployments === 0
      ? undefined
      : `${healthyDeployments.length} healthy · ${totalDeployments} total deployment${totalDeployments === 1 ? '' : 's'}`;

  return (
    <AccessibleTitle title={`${agentName ?? 'Agent'} details for ${workspace}`}>
      <Stack className="h-full min-h-0" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="shrink-0 p-0"
          slotHeading={agent?.name ?? agentName ?? 'Agent details'}
          slotDescription={
            agent?.description ?? 'View and manage this agent, its deployments, and evaluations.'
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
        >
          <Flex align="center" gap="2">
            {statusDetail ? (
              <Tooltip
                side="bottom"
                slotContent={<Text kind="body/regular/sm">{statusDetail}</Text>}
              >
                <span className="cursor-help" role="status">
                  <StatusBadge status={status} label={statusPillLabel} />
                </span>
              </Tooltip>
            ) : (
              <StatusBadge status={status} label={statusPillLabel} />
            )}
          </Flex>
        </PageHeader>

        <TabsRoot
          className="flex min-h-0 flex-1 flex-col"
          value={selectedTab}
          onValueChange={(value) => {
            if (isAgentDetailTab(value)) setSelectedTab(value);
          }}
        >
          <TabsList className="shrink-0">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="traces">Traces</TabsTrigger>
            <TabsTrigger value="evaluations">Evaluations</TabsTrigger>
            <TabsTrigger value="improvements">Improvements</TabsTrigger>
            <TabsTrigger value="deployments">Deployments</TabsTrigger>
            <TabsTrigger value="configuration">Configuration</TabsTrigger>
            <TabsTrigger value="chat">Chat</TabsTrigger>
          </TabsList>

          <TabsContent className="min-h-0 flex-1 overflow-auto p-0 pt-6" value="overview">
            <TabPlaceholder
              icon={LayoutDashboard}
              title="Overview is coming soon"
              description="A summary of this agent's health, recent activity, and open findings will appear here."
            />
          </TabsContent>

          <TabsContent className="min-h-0 flex-1 overflow-auto p-0 pt-6" value="traces">
            <TabPlaceholder
              icon={Waypoints}
              title="Traces are coming soon"
              description="Inspect clustered request traces and drill into failures for this agent. Use Open traces to view them in the monitor for now."
            />
          </TabsContent>

          <TabsContent className="min-h-0 flex-1 overflow-auto p-0 pt-6" value="evaluations">
            <EvaluationsTab
              workspace={workspace}
              evals={agentEvals}
              onRunEvaluation={() => setSubmitEvalOpen(true)}
            />
          </TabsContent>

          <TabsContent className="min-h-0 flex-1 overflow-auto p-0 pt-6" value="improvements">
            <TabPlaceholder
              icon={Sparkles}
              title="Improvements are coming soon"
              description="Validated candidates from optimization runs will show up here for review, comparison, and promotion."
            />
          </TabsContent>

          <TabsContent className="min-h-0 flex-1 overflow-auto p-0 pt-6" value="deployments">
            <DeploymentsTab
              workspace={workspace}
              agentName={agentName}
              deployments={agentDeployments}
              isDeploymentsLoading={isDeploymentsLoading}
              isDeploying={isDeploying}
              onDeploy={() => setCreateDeploymentOpen(true)}
              onChat={switchToChat}
              onDelete={setDeleteDeploymentTarget}
            />
          </TabsContent>

          <TabsContent className="min-h-0 flex-1 overflow-auto p-0 pt-6" value="configuration">
            <ConfigurationTab workspace={workspace} agentName={agentName} agent={agent} />
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
