// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  clearAgentWalkthroughPending,
  hasShownExampleAgentIntro,
  isAgentWalkthroughPending,
  markAgentWalkthroughPending,
  markExampleAgentIntroShown,
} from '@studio/components/sidePanels/AgentPanels/AgentPanel/walkthroughStorage';

describe('agent walkthrough storage', () => {
  beforeEach(() => sessionStorage.clear());

  it('is not pending for an unknown agent', () => {
    expect(isAgentWalkthroughPending('calc')).toBe(false);
  });

  it('marks and reads a pending walkthrough, scoped per agent', () => {
    markAgentWalkthroughPending('calc');
    expect(isAgentWalkthroughPending('calc')).toBe(true);
    expect(isAgentWalkthroughPending('other')).toBe(false);
  });

  it('clears a pending walkthrough', () => {
    markAgentWalkthroughPending('calc');
    clearAgentWalkthroughPending('calc');
    expect(isAgentWalkthroughPending('calc')).toBe(false);
  });
});

describe('example agent intro flag', () => {
  beforeEach(() => sessionStorage.clear());

  it('reports not shown until marked', () => {
    expect(hasShownExampleAgentIntro()).toBe(false);
    markExampleAgentIntroShown();
    expect(hasShownExampleAgentIntro()).toBe(true);
  });
});
