// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getStudioUiNavigationSuggestion } from '@studio/routes/agents/ClaudeCodeChatRoute/studioUiNavigationSuggestions';
import { mockFeatureFlags } from '@studio/tests/util/mockFeatureFlags';

const workspace = 'default';

describe('getStudioUiNavigationSuggestion', () => {
  beforeEach(() => {
    mockFeatureFlags({
      agentsEnabled: true,
      customizerEnabled: true,
      dataDesignerEnabled: true,
      datasetsEnabled: true,
      deploymentsEnabled: true,
      evaluatorEnabled: true,
      guardrailsEnabled: true,
      inferenceProviderEnabled: true,
      modelCompareEnabled: true,
      safeSynthesizerEnabled: true,
      secretsEnabled: true,
      settingsEnabled: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns the matching Studio destination for a product workflow', () => {
    expect(getStudioUiNavigationSuggestion('Add guardrails to an agent', workspace)).toMatchObject({
      id: 'guardrails',
      href: '/workspaces/default/guardrails',
      title: 'Open Guardrails',
    });

    expect(
      getStudioUiNavigationSuggestion('Generate a synthetic dataset for fine tuning', workspace)
    ).toMatchObject({
      id: 'safe-synthesizer-new',
      href: '/workspaces/default/safe-synthesizer/new',
    });
  });

  it('prefers agent-specific evaluation routes over general model evaluations', () => {
    expect(getStudioUiNavigationSuggestion('Evaluate an agent', workspace)).toMatchObject({
      id: 'agent-evaluations',
      href: '/workspaces/default/agents/evaluations',
    });
  });

  it('returns undefined when the matching feature is disabled', () => {
    mockFeatureFlags({ guardrailsEnabled: false });

    expect(getStudioUiNavigationSuggestion('Create guardrails for this agent', workspace)).toBe(
      undefined
    );
  });

  it('does not interrupt ordinary coding-agent prompts', () => {
    expect(getStudioUiNavigationSuggestion('Review the current working tree', workspace)).toBe(
      undefined
    );
    expect(getStudioUiNavigationSuggestion('Fix the settings page component', workspace)).toBe(
      undefined
    );
  });
});
