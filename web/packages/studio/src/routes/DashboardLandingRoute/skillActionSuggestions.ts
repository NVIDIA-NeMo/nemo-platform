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
import { getSkillLookupKeys } from '@studio/routes/DashboardLandingRoute/skillDisplayName';

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

export const isSkillActionEnabled = (template: SkillActionTemplate) =>
  template.requiredFeatureFlags?.every((flag) => featureFlags[flag] !== false) ?? true;

export const getSkillActionSuggestions = (skills: ClaudeCodeSkill[]): SkillActionSuggestion[] => {
  const seenSkills = new Set<string>();
  const suggestions: SkillActionSuggestion[] = [];

  for (const skill of skills) {
    const skillKey = `${skill.name}:${skill.claude_name}`;
    if (seenSkills.has(skillKey)) continue;

    const template = getSkillActionTemplate(skill);
    if (!template || !isSkillActionEnabled(template)) continue;

    seenSkills.add(skillKey);
    suggestions.push({
      ...template,
      skillName: skill.name,
      claudeName: skill.claude_name,
    });
  }

  return suggestions;
};
