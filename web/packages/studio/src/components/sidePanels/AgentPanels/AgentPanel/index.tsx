// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentDeployment } from '@nemo/sdk/generated/agents/schema/AgentDeployment';
import { Block, SegmentedControl, SidePanel, Stack, Text } from '@nvidia/foundations-react-core';
import type { AgentConfig } from '@studio/components/dataViews/AgentsDataView';
import { getAgentModelNames } from '@studio/components/dataViews/AgentsDataView/utils';
import { DeleteConfirmationModal } from '@studio/components/DeleteConfirmationModal';
import { AgentDetailsContent } from '@studio/components/sidePanels/AgentPanels/AgentPanel/AgentDetailsContent';
import { ChatPlaygroundContent } from '@studio/components/sidePanels/AgentPanels/AgentPanel/ChatPlaygroundContent';
import { DeploymentLogsView } from '@studio/components/sidePanels/AgentPanels/AgentPanel/DeploymentLogsView';
import type { AgentPanelTab } from '@studio/components/sidePanels/AgentPanels/AgentPanel/types';
import { useAgentPanel } from '@studio/components/sidePanels/AgentPanels/AgentPanel/useAgentPanel';
import { deriveWalkthroughStep } from '@studio/components/sidePanels/AgentPanels/AgentPanel/walkthrough';
import { WalkthroughCoachmarks } from '@studio/components/sidePanels/AgentPanels/AgentPanel/WalkthroughCoachmarks';
import {
  clearAgentWalkthroughPending,
  isAgentWalkthroughPending,
} from '@studio/components/sidePanels/AgentPanels/AgentPanel/walkthroughStorage';
import { CreateDeploymentModal } from '@studio/routes/agents/AgentDeploymentsListRoute/CreateDeploymentModal';
import { SubmitEvaluationModal } from '@studio/routes/agents/AgentEvaluationsRoute/components/SubmitEvaluationModal';
import { type ComponentProps, type FC, useEffect, useMemo, useRef, useState } from 'react';

export type { AgentPanelTab };

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
  const [selectedTab, setSelectedTab] = useState<AgentPanelTab>(defaultTab ?? 'agent-details');
  const [selectedDeploymentName, setSelectedDeploymentName] = useState<string | undefined>();
  const [deleteDeploymentTarget, setDeleteDeploymentTarget] = useState<AgentDeployment | null>(
    null
  );
  const [submitEvalOpen, setSubmitEvalOpen] = useState(false);
  const [createDeploymentOpen, setCreateDeploymentOpen] = useState(false);
  const [walkthroughActive, setWalkthroughActive] = useState(false);
  const [walkthroughDismissed, setWalkthroughDismissed] = useState(false);
  const deployButtonRef = useRef<HTMLDivElement>(null);
  const tabsRef = useRef<HTMLDivElement>(null);
  const chatAreaRef = useRef<HTMLDivElement>(null);

  const tabItems = useMemo(
    () => [
      { value: 'agent-details', children: 'Details' },
      { value: 'chat-playground', children: 'Chat Playground' },
      { value: 'deployment-logs', children: 'Logs' },
    ],
    []
  );

  useEffect(() => {
    if (defaultTab) setSelectedTab(defaultTab);
  }, [defaultTab]);

  useEffect(() => {
    setSelectedDeploymentName(undefined);
    setWalkthroughDismissed(false);
    setWalkthroughActive(!!agentName && isAgentWalkthroughPending(agentName));
  }, [agentName]);

  const {
    isDeploymentsLoading,
    agent,
    agentDeployments,
    agentEvals,
    healthyDeployments,
    isDeploying,
    chatDeployment,
    deleteDeploymentMutation,
  } = useAgentPanel({ workspace, agentName, selectedDeploymentName });

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

  const switchToChat = (deployment: AgentDeployment) => {
    setSelectedDeploymentName(deployment.name);
    setSelectedTab('chat-playground');
    onTabChange?.('chat-playground');
  };

  const agentModelNames = getAgentModelNames(agent?.config as AgentConfig | undefined);

  let content: React.ReactNode;

  if (selectedTab === 'deployment-logs') {
    content = <DeploymentLogsView workspace={workspace} deployments={agentDeployments} />;
  } else if (selectedTab === 'chat-playground') {
    content = (
      <ChatPlaygroundContent
        workspace={workspace}
        agentName={agentName}
        chatDeployment={chatDeployment}
        healthyDeployments={healthyDeployments}
        isDeploymentsLoading={isDeploymentsLoading}
        isDeploying={isDeploying}
        chatAreaRef={chatAreaRef}
        onSelectDeployment={(v) => setSelectedDeploymentName(v)}
        onDeploy={() => setCreateDeploymentOpen(true)}
      />
    );
  } else {
    content = (
      <AgentDetailsContent
        workspace={workspace}
        agentName={agentName}
        agent={agent}
        agentDeployments={agentDeployments}
        agentEvals={agentEvals}
        isDeploymentsLoading={isDeploymentsLoading}
        isDeploying={isDeploying}
        walkthroughStep={walkthroughStep}
        deployButtonRef={deployButtonRef}
        onSubmitEval={() => setSubmitEvalOpen(true)}
        onDeploy={() => setCreateDeploymentOpen(true)}
        onSwitchToChat={switchToChat}
        onDeleteDeployment={(deployment) => setDeleteDeploymentTarget(deployment)}
      />
    );
  }

  return (
    <>
      <SidePanel
        open={open}
        onOpenChange={onOpenChange}
        slotHeading={
          <Stack gap="1">
            <Text kind="inherit">{agentName}</Text>
            {agentModelNames.length > 0 && (
              <Text kind="body/regular/sm" className="text-secondary">
                {agentModelNames.join(', ')}
              </Text>
            )}
          </Stack>
        }
        bordered
        modal
        className="[&.nv-side-panel-content]:w-full [&.nv-side-panel-content]:max-w-[50vw] [&_.nv-side-panel-main]:gap-4 [&_.nv-side-panel-main]:p-0"
        {...attributes?.SidePanel}
      >
        <div ref={tabsRef} className="w-full">
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
        </div>
        {content}
        <WalkthroughCoachmarks
          walkthroughStep={walkthroughStep}
          deployButtonRef={deployButtonRef}
          tabsRef={tabsRef}
          chatAreaRef={chatAreaRef}
          onDismiss={endWalkthrough}
        />
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
