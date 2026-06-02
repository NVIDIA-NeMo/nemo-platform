// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { JOB_POLLING_INTERVAL_LONG, JOB_POLLING_INTERVAL_MS } from '@nemo/common/src/constants';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { isDefined } from '@nemo/common/src/utils/list';
import {
  getAgentsListDeploymentsQueryKey,
  useAgentsDeleteDeployment,
  useAgentsListAgents,
  useAgentsListDeployments,
} from '@nemo/sdk/generated/agents/api';
import type { AgentDeployment } from '@nemo/sdk/generated/agents/schema/AgentDeployment';
import {
  Accordion,
  Block,
  Button,
  Flex,
  SegmentedControl,
  Select,
  SidePanel,
  Stack,
  StatusIndicator,
  Text,
} from '@nvidia/foundations-react-core';
import type { AgentConfig } from '@studio/components/dataViews/AgentsDataView';
import { getAgentModelNames } from '@studio/components/dataViews/AgentsDataView/utils';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { ModelChat } from '@studio/components/ModelChat';
import { NoHealthyDeploymentsBanner } from '@studio/components/sidePanels/AgentPanels/AgentPanel/NoHealthyDeploymentsBanner';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { CreateDeploymentModal } from '@studio/routes/agents/AgentDeploymentsListRoute/CreateDeploymentModal';
import { fetchAgentEvalJobs } from '@studio/routes/agents/AgentEvaluationsRoute/api';
import { SubmitEvaluationModal } from '@studio/routes/agents/AgentEvaluationsRoute/components/SubmitEvaluationModal';
import { getAgentEvaluationDetailRoute, getAgentEvaluationsListRoute } from '@studio/routes/utils';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { type ComponentProps, type FC, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

const RECENT_EVAL_LIMIT = 5;

export type AgentPanelTab = 'agent-details' | 'chat-playground';

function deploymentStatusColor(status?: string): 'green' | 'red' | 'yellow' | undefined {
  if (status === 'running') return 'green';
  if (status === 'error' || status === 'failed') return 'red';
  if (status === 'pending' || status === 'starting' || status === 'deleting') return 'yellow';
  return undefined;
}

export interface AgentPanelProps {
  agentName?: string;
  workspace: string;
  open?: boolean;
  defaultTab?: AgentPanelTab;
  onTabChange?: (tab: AgentPanelTab) => void;
  onOpenChange?: (open: boolean) => void;
  attributes?: {
    SidePanel?: ComponentProps<typeof SidePanel>;
    SegmentedControl?: ComponentProps<typeof SegmentedControl>;
  };
}

export const AgentPanel: FC<AgentPanelProps> = ({
  agentName,
  workspace,
  open = true,
  defaultTab,
  onTabChange,
  onOpenChange,
  attributes,
}) => {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [selectedTab, setSelectedTab] = useState<AgentPanelTab>(defaultTab ?? 'agent-details');
  const [selectedDeploymentName, setSelectedDeploymentName] = useState<string | undefined>();
  const [deleteDeploymentTarget, setDeleteDeploymentTarget] = useState<AgentDeployment | null>(
    null
  );
  const [submitEvalOpen, setSubmitEvalOpen] = useState(false);
  const [createDeploymentOpen, setCreateDeploymentOpen] = useState(false);

  const tabItems = useMemo(
    () => [
      { value: 'agent-details', children: 'Details' },
      { value: 'chat-playground', children: 'Chat Playground' },
    ],
    []
  );

  useEffect(() => {
    if (defaultTab) setSelectedTab(defaultTab);
  }, [defaultTab]);

  useEffect(() => {
    setSelectedDeploymentName(undefined);
  }, [agentName]);

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

  const switchToChat = (deployment: AgentDeployment) => {
    setSelectedDeploymentName(deployment.name);
    setSelectedTab('chat-playground');
    onTabChange?.('chat-playground');
  };

  let content: React.ReactNode;

  if (selectedTab === 'chat-playground') {
    const deploymentSelectItems = healthyDeployments.flatMap((d) =>
      d.name ? [{ value: d.name, children: d.name }] : []
    );
    const noHealthyDeployments = !isDeploymentsLoading && healthyDeployments.length === 0;

    content = (
      <Stack className="h-full min-h-0" gap="0">
        {!noHealthyDeployments && healthyDeployments.length > 1 && (
          <Block padding="4" className="border-b border-base shrink-0">
            <Select
              value={chatDeployment?.name ?? ''}
              items={deploymentSelectItems}
              onValueChange={(v) => setSelectedDeploymentName(v)}
            />
          </Block>
        )}
        {noHealthyDeployments && (
          <Block padding="4" className="shrink-0">
            <NoHealthyDeploymentsBanner
              agentName={agentName}
              isDeploying={isDeploying}
              onDeploy={() => setCreateDeploymentOpen(true)}
            />
          </Block>
        )}
        <Block className="flex-1 min-h-0" padding="4">
          <ModelChat
            model={chatDeployment?.name ?? agentName ?? ''}
            workspace={workspace}
            baseURL={
              chatDeployment
                ? `${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/${workspace}/deployments/${chatDeployment.name}/-/v1`
                : undefined
            }
            disabled={noHealthyDeployments}
          />
        </Block>
      </Stack>
    );
  } else {
    content = (
      <Stack className="overflow-auto">
        <Block padding="4">
          <Stack gap="3">
            <Text kind="body/semibold/xl">{agentName}</Text>
            {isDefined(agent?.description) && agent.description && (
              <Text kind="body/regular/sm" color="secondary">
                {agent.description}
              </Text>
            )}
            <Flex gap="2" align="center">
              <Button
                className="flex-1"
                kind="secondary"
                onClick={() => setSubmitEvalOpen(true)}
                disabled={!agentName}
              >
                Evaluate this Agent
              </Button>
            </Flex>
          </Stack>
        </Block>
        <Accordion
          multiple
          className="w-full border-t border-base"
          defaultValue={['agent-details', 'deployments', 'evaluations']}
          items={[
            {
              chevronPosition: 'start',
              slotTrigger: 'Agent Details',
              slotContent: (
                <Stack gap="2">
                  <KVPair label="Name" value={agent?.name ?? agentName} />
                  <KVPair label="Workspace" value={agent?.workspace ?? workspace} />
                  {isDefined(agent?.description) && (
                    <KVPair label="Description" value={agent.description || '-'} />
                  )}
                  {(() => {
                    const models = getAgentModelNames(agent?.config as AgentConfig | undefined);
                    return models.length > 0 ? (
                      <KVPair label="Model" value={models.join(', ')} />
                    ) : null;
                  })()}
                  {isDefined(agent?.config_format) && (
                    <KVPair label="Config Format" value={agent.config_format} />
                  )}
                </Stack>
              ),
              value: 'agent-details',
            },
            {
              chevronPosition: 'start',
              slotTrigger: 'Deployments',
              slotContent:
                !isDeploymentsLoading && agentDeployments.length === 0 ? (
                  <NoHealthyDeploymentsBanner
                    agentName={agentName}
                    isDeploying={isDeploying}
                    onDeploy={() => setCreateDeploymentOpen(true)}
                    message="No deployments for this agent."
                  />
                ) : (
                  <Stack gap="0" className="-mx-4 -mb-4">
                    {agentDeployments.map((deployment) => (
                      <Flex
                        key={deployment.name}
                        align="center"
                        gap="2"
                        className="px-4 py-3 border-b border-base last:border-b-0"
                      >
                        <StatusIndicator
                          color={deploymentStatusColor(deployment.status)}
                          size="small"
                        />
                        <Stack gap="0" className="flex-1 min-w-0">
                          <Text kind="body/semibold/sm">{deployment.name}</Text>
                          {deployment.endpoint && (
                            <Text kind="body/regular/xs" color="secondary" className="truncate">
                              {deployment.endpoint}
                            </Text>
                          )}
                          {deployment.error && (
                            <Text kind="body/regular/xs" color="danger" className="truncate">
                              {deployment.error}
                            </Text>
                          )}
                        </Stack>
                        <StatusBadge status={deployment.status} />
                        <Flex gap="1" className="shrink-0">
                          <Button
                            kind="tertiary"
                            size="small"
                            disabled={deployment.status !== 'running'}
                            onClick={() => switchToChat(deployment)}
                          >
                            Chat
                          </Button>
                          <Button
                            kind="tertiary"
                            size="small"
                            color="danger"
                            onClick={() => setDeleteDeploymentTarget(deployment)}
                          >
                            Delete
                          </Button>
                        </Flex>
                      </Flex>
                    ))}
                  </Stack>
                ),
              value: 'deployments',
            },
            {
              chevronPosition: 'start' as const,
              slotTrigger: 'Recent Evaluations',
              slotContent:
                agentEvals.length === 0 ? (
                  <Stack gap="2">
                    <Text color="secondary">No evaluation jobs found for this agent.</Text>
                    <Block>
                      <Link to={getAgentEvaluationsListRoute(workspace)} className="text-xs">
                        View all evaluations →
                      </Link>
                    </Block>
                  </Stack>
                ) : (
                  <Stack gap="0" className="-mx-4 -mb-4">
                    {agentEvals.map((job) => (
                      <Link
                        key={job.name}
                        to={getAgentEvaluationDetailRoute(workspace, job.name)}
                        className="no-underline text-inherit"
                      >
                        <Flex
                          align="center"
                          gap="2"
                          className="px-4 py-3 border-b border-base last:border-b-0 hover:bg-surface-hover"
                        >
                          <Stack gap="0" className="flex-1 min-w-0">
                            <Text kind="body/semibold/sm" className="truncate">
                              {job.name}
                            </Text>
                            <Text kind="body/regular/xs" color="secondary">
                              <RelativeTime datetime={job.created_at} />
                            </Text>
                          </Stack>
                          <StatusBadge status={job.status} />
                        </Flex>
                      </Link>
                    ))}
                    <Block className="px-4 py-3 border-t border-base">
                      <Link to={getAgentEvaluationsListRoute(workspace)} className="text-xs">
                        View all evaluations →
                      </Link>
                    </Block>
                  </Stack>
                ),
              value: 'evaluations',
            },
          ]}
        />
      </Stack>
    );
  }

  return (
    <>
      <SidePanel
        open={open}
        onOpenChange={onOpenChange}
        slotHeading={agentName}
        bordered
        modal
        className="[&.nv-side-panel-content]:w-[600px] [&_.nv-side-panel-main]:gap-4 [&_.nv-side-panel-main]:p-0"
        {...attributes?.SidePanel}
      >
        <Block className="w-full px-4">
          <SegmentedControl
            className="[&.nv-segmented-control-root]:mt-4 w-full!"
            value={selectedTab}
            items={tabItems}
            onValueChange={(v) => {
              const tab = v as AgentPanelTab;
              setSelectedTab(tab);
              onTabChange?.(tab);
            }}
            {...attributes?.SegmentedControl}
          />
        </Block>
        {content}
      </SidePanel>
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
              // Error already surfaced via onError toast
              return false;
            }
          }}
          onClose={() => setDeleteDeploymentTarget(null)}
          simpleConfirm
        />
      )}
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
    </>
  );
};
