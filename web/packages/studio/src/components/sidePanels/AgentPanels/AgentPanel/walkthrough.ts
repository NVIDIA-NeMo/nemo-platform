// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentPanelTab } from '@studio/components/sidePanels/AgentPanels/AgentPanel/types';

export type WalkthroughStep = 'deploy' | 'switch-to-chat' | 'wait' | 'chat';

export interface WalkthroughState {
  active: boolean;
  dismissed: boolean;
  createDeploymentOpen: boolean;
  selectedTab: AgentPanelTab;
  hasDeployment: boolean;
  hasHealthyDeployment: boolean;
}

// Derived each render from panel state — the walkthrough advances on real
// actions (deploy → switch tab → deployment running), not Next buttons.
export const deriveWalkthroughStep = (s: WalkthroughState): WalkthroughStep | null => {
  if (!s.active || s.dismissed || s.createDeploymentOpen) return null;
  if (!s.hasDeployment) return s.selectedTab === 'agent-details' ? 'deploy' : null;
  if (s.selectedTab !== 'chat-playground') return 'switch-to-chat';
  return s.hasHealthyDeployment ? 'chat' : 'wait';
};

export const WALKTHROUGH_COPY: Record<WalkthroughStep, { title: string; body: string }> = {
  deploy: {
    title: 'Deploy your agent',
    body: 'An agent needs a running deployment before you can use it. Click "Deploy this Agent" to start one.',
  },
  'switch-to-chat': {
    title: 'Open the chat',
    body: 'Your deployment is starting. Switch to the Chat Playground tab to watch it come up and talk to your agent.',
  },
  wait: {
    title: 'Deployment starting',
    body: 'Hang tight — the deployment needs a moment to finish starting. The chat unlocks as soon as it is running.',
  },
  chat: {
    title: 'Your agent is live',
    body: 'The deployment is running. Send it a message to start chatting.',
  },
};
