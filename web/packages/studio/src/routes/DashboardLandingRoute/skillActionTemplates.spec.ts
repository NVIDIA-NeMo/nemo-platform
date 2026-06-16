// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ClaudeCodeSkill } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import { getSkillActionSuggestions } from '@studio/routes/DashboardLandingRoute/skillActionSuggestions';
import { mockFeatureFlags } from '@studio/tests/util/mockFeatureFlags';

const skill = (overrides: Partial<ClaudeCodeSkill>): ClaudeCodeSkill => ({
  name: 'inference',
  claude_name: 'nemo-inference',
  description: 'Use NeMo Platform inference.',
  source: 'nemo-platform',
  install_path: '.claude/skills/nemo-inference/SKILL.md',
  installed: false,
  ...overrides,
});

describe('getSkillActionSuggestions', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('resolves templates from claude install names without alias tables', () => {
    mockFeatureFlags({ inferenceProviderEnabled: true });

    const [suggestion] = getSkillActionSuggestions([
      skill({ name: 'inference', claude_name: 'nemo-inference' }),
    ]);

    expect(suggestion?.title).toBe('Configure inference');
    expect(suggestion?.skillName).toBe('inference');
  });

  it('ignores skills without curated templates', () => {
    expect(
      getSkillActionSuggestions([
        skill({
          name: 'custom-plugin-skill',
          claude_name: 'nemo-custom-plugin-skill',
          description: 'A plugin-specific workflow.',
        }),
      ])
    ).toEqual([]);
  });

  it('filters curated templates when required feature flags are disabled', () => {
    mockFeatureFlags({ guardrailsEnabled: false });

    expect(
      getSkillActionSuggestions([
        skill({ name: 'nemo-guardrails', claude_name: 'nemo-nemo-guardrails' }),
      ])
    ).toEqual([]);
  });
});
