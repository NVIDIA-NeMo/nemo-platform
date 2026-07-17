// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { summarizeAgentCard } from '@studio/components/sidePanels/AgentPanels/AgentPanel/summarizeAgentCard';

describe('summarizeAgentCard', () => {
  it('extracts name, description, and skills', () => {
    expect(
      summarizeAgentCard({
        name: 'Calculator Agent',
        description: 'does math',
        skills: [
          { id: 'calculator__add', name: 'add', description: 'Add numbers' },
          { id: 'calculator__divide', name: 'divide' },
        ],
      })
    ).toEqual({
      name: 'Calculator Agent',
      description: 'does math',
      skills: [
        { id: 'calculator__add', name: 'add', description: 'Add numbers' },
        { id: 'calculator__divide', name: 'divide', description: undefined },
      ],
    });
  });

  it('returns empty skills for undefined or malformed card', () => {
    expect(summarizeAgentCard(undefined).skills).toEqual([]);
    expect(summarizeAgentCard({ skills: 'nope' }).skills).toEqual([]);
    expect(summarizeAgentCard({ skills: [null, 42, {}] }).skills).toEqual([]);
  });

  it('falls back to id when a skill has no name', () => {
    expect(summarizeAgentCard({ skills: [{ id: 'only_id' }] }).skills).toEqual([
      { id: 'only_id', name: 'only_id', description: undefined },
    ]);
  });
});
