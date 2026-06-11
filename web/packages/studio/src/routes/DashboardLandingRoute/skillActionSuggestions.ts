// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { featureFlags } from '@studio/constants/featureFlags';
import type { ClaudeCodeSkill } from '@studio/routes/agents/ClaudeCodeChatRoute/types';
import {
  SKILL_ACTION_TEMPLATES,
  type SkillActionSuggestion,
  type SkillActionTemplate,
  type SkillActionTemplateName,
} from '@studio/routes/DashboardLandingRoute/skillActionTemplateCatalog';
import {
  getSkillDisplayName,
  getSkillLookupKeys,
} from '@studio/routes/DashboardLandingRoute/skillDisplayName';
import { Wrench } from 'lucide-react';
import { createElement } from 'react';

export type {
  SkillActionSuggestion,
  SkillActionTemplate,
} from '@studio/routes/DashboardLandingRoute/skillActionTemplateCatalog';

const isSkillActionTemplateName = (skillName: string): skillName is SkillActionTemplateName =>
  Object.prototype.hasOwnProperty.call(SKILL_ACTION_TEMPLATES, skillName);

const getSkillActionTemplate = (skill: ClaudeCodeSkill): SkillActionTemplate | undefined => {
  for (const lookupKey of getSkillLookupKeys(skill)) {
    if (isSkillActionTemplateName(lookupKey)) {
      return SKILL_ACTION_TEMPLATES[lookupKey];
    }
  }

  return undefined;
};

const getFallbackSkillActionTemplate = (skill: ClaudeCodeSkill): SkillActionTemplate => ({
  title: getSkillDisplayName(skill),
  description: skill.description || 'Use this NeMo Platform skill in Claude Code.',
  prompt: `Use the ${skill.name} skill for this NeMo Platform task. Inspect the workspace first and ask for anything missing before acting.`,
  icon: createElement(Wrench, { size: 18 }),
});

export const isSkillActionEnabled = (template: SkillActionTemplate) =>
  template.requiredFeatureFlags?.every((flag) => featureFlags[flag] !== false) ?? true;

export const getSkillActionSuggestions = (skills: ClaudeCodeSkill[]): SkillActionSuggestion[] => {
  const seenSkills = new Set<string>();
  const suggestions: SkillActionSuggestion[] = [];

  for (const skill of skills) {
    const skillKey = `${skill.name}:${skill.claude_name}`;
    if (seenSkills.has(skillKey)) continue;

    const template = getSkillActionTemplate(skill) ?? getFallbackSkillActionTemplate(skill);
    if (!isSkillActionEnabled(template)) continue;

    seenSkills.add(skillKey);
    suggestions.push({
      ...template,
      skillName: skill.name,
      claudeName: skill.claude_name,
    });
  }

  return suggestions;
};
