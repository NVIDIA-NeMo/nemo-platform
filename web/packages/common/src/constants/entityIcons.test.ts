// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ENTITY_EMPTY_STATES } from '@nemo/common/src/components/EntityEmptyState/registry';
import { ENTITY_ICONS } from '@nemo/common/src/constants/entityIcons';

describe('ENTITY_ICONS', () => {
  it('covers exactly the entities in the empty-state registry', () => {
    expect(Object.keys(ENTITY_ICONS).sort()).toEqual(Object.keys(ENTITY_EMPTY_STATES).sort());
  });

  it('maps every entity to a renderable icon', () => {
    for (const [entity, icon] of Object.entries(ENTITY_ICONS)) {
      expect(icon, `${entity} has no icon`).toBeTruthy();
    }
  });

  it('gives sub-entities the same glyph family as their parent', () => {
    // Traces are one entity across Intake and Insights.
    expect(ENTITY_ICONS.insightTraces).toBe(ENTITY_ICONS.telemetryTraces);
    // Monitor runs are agent invocations.
    expect(ENTITY_ICONS.agentMonitorRuns).toBe(ENTITY_ICONS.agents);
    // Evaluation surfaces all read as evaluations.
    expect(ENTITY_ICONS.agentEvaluations).toBe(ENTITY_ICONS.evaluationResults);
    expect(ENTITY_ICONS.evaluationSessions).toBe(ENTITY_ICONS.evaluationResults);
    expect(ENTITY_ICONS.insightExperiments).toBe(ENTITY_ICONS.experiments);
  });

  it('does not reuse one glyph across unrelated entities', () => {
    // The intentional families above. Everything else must own its glyph
    // outright — a shared glyph is how `ShieldCheck` and `Radar` stopped
    // meaning anything specific (ASTD-447).
    const aliases = new Set([
      'insightTraces',
      'agentMonitorRuns',
      'agentEvaluations',
      'evaluationSessions',
      'insightExperiments',
    ]);
    const distinct = Object.entries(ENTITY_ICONS).filter(([entity]) => !aliases.has(entity));

    expect(new Set(distinct.map(([, icon]) => icon)).size).toBe(distinct.length);
  });
});
