// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentCard } from '@nemo/sdk/generated/agents/schema/AgentCard';

export interface AgentCardSkill {
  id: string;
  name: string;
  description?: string;
}

export interface AgentCardSummary {
  name?: string;
  description?: string;
  skills: AgentCardSkill[];
}

const asString = (v: unknown): string | undefined => (typeof v === 'string' ? v : undefined);

/**
 * Reads the display-relevant fields out of a fetched A2A agent card. The card
 * is stored loosely (a plain dict), so every access is defensive; unknown
 * shapes degrade to an empty skills list rather than throwing.
 */
export const summarizeAgentCard = (card: AgentCard | undefined): AgentCardSummary => {
  const rawSkills = Array.isArray((card as { skills?: unknown } | undefined)?.skills)
    ? ((card as { skills: unknown[] }).skills as unknown[])
    : [];

  const skills: AgentCardSkill[] = rawSkills.flatMap((entry, i) => {
    if (!entry || typeof entry !== 'object') return [];
    const s = entry as Record<string, unknown>;
    const name = asString(s.name) ?? asString(s.id);
    if (!name) return [];
    return [{ id: asString(s.id) ?? `skill-${i}`, name, description: asString(s.description) }];
  });

  return {
    name: asString((card as Record<string, unknown> | undefined)?.name),
    description: asString((card as Record<string, unknown> | undefined)?.description),
    skills,
  };
};
