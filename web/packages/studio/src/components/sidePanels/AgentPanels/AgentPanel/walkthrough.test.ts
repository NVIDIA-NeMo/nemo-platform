// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  deriveWalkthroughStep,
  type WalkthroughState,
} from '@studio/components/sidePanels/AgentPanels/AgentPanel/walkthrough';

const base: WalkthroughState = {
  active: true,
  dismissed: false,
  createDeploymentOpen: false,
  selectedTab: 'agent-details',
  hasDeployment: false,
  hasHealthyDeployment: false,
};

describe('deriveWalkthroughStep', () => {
  it('returns null when inactive, dismissed, or a deploy modal is open', () => {
    expect(deriveWalkthroughStep({ ...base, active: false })).toBeNull();
    expect(deriveWalkthroughStep({ ...base, dismissed: true })).toBeNull();
    expect(deriveWalkthroughStep({ ...base, createDeploymentOpen: true })).toBeNull();
  });

  it('prompts to deploy on the details tab before any deployment exists', () => {
    expect(deriveWalkthroughStep(base)).toBe('deploy');
  });

  it('does not prompt to deploy on other tabs before a deployment exists', () => {
    expect(deriveWalkthroughStep({ ...base, selectedTab: 'chat-playground' })).toBeNull();
  });

  it('points to the chat tab once a deployment exists but the user is elsewhere', () => {
    expect(deriveWalkthroughStep({ ...base, hasDeployment: true })).toBe('switch-to-chat');
    expect(
      deriveWalkthroughStep({ ...base, hasDeployment: true, selectedTab: 'deployment-logs' })
    ).toBe('switch-to-chat');
  });

  it('shows the wait step on the chat tab while the deployment is still starting', () => {
    expect(
      deriveWalkthroughStep({ ...base, hasDeployment: true, selectedTab: 'chat-playground' })
    ).toBe('wait');
  });

  it('shows the chat step once a healthy deployment is running', () => {
    expect(
      deriveWalkthroughStep({
        ...base,
        hasDeployment: true,
        hasHealthyDeployment: true,
        selectedTab: 'chat-playground',
      })
    ).toBe('chat');
  });
});
