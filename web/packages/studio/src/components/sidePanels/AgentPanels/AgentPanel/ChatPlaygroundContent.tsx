// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentDeployment } from '@nemo/sdk/generated/agents/schema/AgentDeployment';
import { Block, Select, Stack, Text } from '@nvidia/foundations-react-core';
import { ModelChat } from '@studio/components/ModelChat';
import { NoHealthyDeploymentsBanner } from '@studio/components/sidePanels/AgentPanels/AgentPanel/NoHealthyDeploymentsBanner';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { Globe } from 'lucide-react';
import type { FC, RefObject } from 'react';

interface ChatPlaygroundContentProps {
  workspace: string;
  agentName?: string;
  chatDeployment?: AgentDeployment;
  healthyDeployments: AgentDeployment[];
  isDeploymentsLoading: boolean;
  isDeploying: boolean;
  isExternal?: boolean;
  externalEndpoint?: string;
  chatAreaRef: RefObject<HTMLDivElement | null>;
  onSelectDeployment: (name: string) => void;
  onDeploy: () => void;
}

export const ChatPlaygroundContent: FC<ChatPlaygroundContentProps> = ({
  workspace,
  agentName,
  chatDeployment,
  healthyDeployments,
  isDeploymentsLoading,
  isDeploying,
  isExternal,
  externalEndpoint,
  chatAreaRef,
  onSelectDeployment,
  onDeploy,
}) => {
  const deploymentSelectItems = healthyDeployments.flatMap((d) =>
    d.name
      ? [
          {
            value: d.name,
            children: d.status ? `${d.name} · ${d.status}` : d.name,
          },
        ]
      : []
  );
  const noHealthyDeployments = !isDeploymentsLoading && healthyDeployments.length === 0;

  // External agents run outside NeMo Platform, so there's no deployment to
  // chat through. Direct chat (A2A) isn't wired up yet — show a clear message
  // instead of the managed "no deployment / deploy" flow.
  if (isExternal) {
    return (
      <div ref={chatAreaRef} className="flex flex-col h-full min-h-0">
        <Block padding="4">
          <Stack gap="2" align="center" className="pt-8 text-center">
            <Globe className="size-8 text-subtle" />
            <Text kind="body/semibold/md">This agent runs outside NeMo Platform</Text>
            <Text kind="body/regular/sm" color="secondary">
              There is no NeMo deployment to chat with. Chat with it directly at its own endpoint
              {externalEndpoint ? `: ${externalEndpoint}` : '.'}
            </Text>
          </Stack>
        </Block>
      </div>
    );
  }

  return (
    <div ref={chatAreaRef} className="flex flex-col h-full min-h-0">
      {!noHealthyDeployments && healthyDeployments.length > 1 && (
        <Block padding="4" className="border-b border-base shrink-0">
          <Select
            value={chatDeployment?.name ?? ''}
            items={deploymentSelectItems}
            onValueChange={(v) => onSelectDeployment(v)}
          />
        </Block>
      )}
      {noHealthyDeployments ? (
        <Block padding="4" className="shrink-0">
          <NoHealthyDeploymentsBanner
            agentName={agentName}
            isDeploying={isDeploying}
            onDeploy={onDeploy}
          />
        </Block>
      ) : (
        <Block className="flex-1 min-h-0" padding="4">
          <ModelChat
            model={chatDeployment?.name ?? agentName ?? ''}
            workspace={workspace}
            baseURL={
              chatDeployment
                ? `${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/${workspace}/deployments/${chatDeployment.name}/-/v1`
                : undefined
            }
            disabled={isDeploymentsLoading || !chatDeployment}
          />
        </Block>
      )}
    </div>
  );
};
