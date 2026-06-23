// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { isDefined } from '@nemo/common/src/utils/list';
import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import type { AgentDeployment } from '@nemo/sdk/generated/agents/schema/AgentDeployment';
import {
  Accordion,
  Block,
  Button,
  Flex,
  Stack,
  StatusIndicator,
  Text,
} from '@nvidia/foundations-react-core';
import type { AgentConfig } from '@studio/components/dataViews/AgentsDataView';
import { getAgentModelNames } from '@studio/components/dataViews/AgentsDataView/utils';
import { deploymentStatusColor } from '@studio/components/sidePanels/AgentPanels/AgentPanel/helpers';
import { NoHealthyDeploymentsBanner } from '@studio/components/sidePanels/AgentPanels/AgentPanel/NoHealthyDeploymentsBanner';
import type { WalkthroughStep } from '@studio/components/sidePanels/AgentPanels/AgentPanel/walkthrough';
import type { AgentEvalJob } from '@studio/routes/agents/AgentEvaluationsRoute/api';
import { getAgentEvaluationDetailRoute, getAgentEvaluationsListRoute } from '@studio/routes/utils';
import type { FC, RefObject } from 'react';
import { Link } from 'react-router-dom';

interface AgentDetailsContentProps {
  workspace: string;
  agentName?: string;
  agent?: Agent;
  agentDeployments: AgentDeployment[];
  agentEvals: AgentEvalJob[];
  isDeploymentsLoading: boolean;
  isDeploying: boolean;
  walkthroughStep: WalkthroughStep | null;
  deployButtonRef: RefObject<HTMLDivElement | null>;
  onSubmitEval: () => void;
  onDeploy: () => void;
  onSwitchToChat: (deployment: AgentDeployment) => void;
  onDeleteDeployment: (deployment: AgentDeployment) => void;
}

export const AgentDetailsContent: FC<AgentDetailsContentProps> = ({
  workspace,
  agentName,
  agent,
  agentDeployments,
  agentEvals,
  isDeploymentsLoading,
  isDeploying,
  walkthroughStep,
  deployButtonRef,
  onSubmitEval,
  onDeploy,
  onSwitchToChat,
  onDeleteDeployment,
}) => (
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
          <Button className="flex-1" kind="primary" onClick={onSubmitEval} disabled={!agentName}>
            Evaluate this Agent
          </Button>
          <div
            ref={deployButtonRef}
            className={`flex-1 rounded-md ${
              walkthroughStep === 'deploy' ? 'ring-2 ring-brand ring-offset-2 animate-pulse' : ''
            }`}
          >
            <Button
              className="w-full"
              kind="secondary"
              onClick={onDeploy}
              disabled={!agentName || isDeploying}
            >
              {isDeploying ? 'Deploying…' : 'Deploy this Agent'}
            </Button>
          </div>
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
                onDeploy={onDeploy}
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
                        onClick={() => onSwitchToChat(deployment)}
                      >
                        Chat
                      </Button>
                      <Button
                        kind="tertiary"
                        size="small"
                        color="danger"
                        onClick={() => onDeleteDeployment(deployment)}
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
