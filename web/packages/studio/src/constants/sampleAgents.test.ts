// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  isSampleAgentName,
  SAMPLE_AGENTS,
  sampleAgentKeyForAgentName,
} from '@studio/constants/sampleAgents';

describe('sampleAgentKeyForAgentName', () => {
  it('matches a generated example agent name to its key', () => {
    expect(sampleAgentKeyForAgentName('email-phishing-demo-agent-9lhh53')).toBe(
      'email_phishing_analyzer'
    );
    expect(sampleAgentKeyForAgentName('calculator-demo-agent-abc123')).toBe('calculator');
  });

  it('returns undefined for non-example agents and empty input', () => {
    expect(sampleAgentKeyForAgentName('my-custom-agent')).toBeUndefined();
    expect(sampleAgentKeyForAgentName(undefined)).toBeUndefined();
    expect(sampleAgentKeyForAgentName('')).toBeUndefined();
  });

  it('requires the prefix separator (no partial-token match)', () => {
    // 'calculator-demo-agentx-...' is not a real 'calculator-demo-agent-' name.
    expect(sampleAgentKeyForAgentName('calculator-demo-agentxyz')).toBeUndefined();
  });

  it('picks the longest matching prefix when one is a substring of another', () => {
    const registry = [
      { namePrefix: 'test', key: 'short' },
      { namePrefix: 'test-agent', key: 'long' },
    ];
    const match = (name: string) =>
      registry
        .filter((a) => name.startsWith(`${a.namePrefix}-`))
        .sort((a, b) => b.namePrefix.length - a.namePrefix.length)[0]?.key;
    expect(match('test-agent-abc123')).toBe('long');
    expect(match('test-abc123')).toBe('short');
  });

  it('every registry prefix resolves to its own key', () => {
    for (const agent of SAMPLE_AGENTS) {
      expect(sampleAgentKeyForAgentName(`${agent.namePrefix}-zzzz99`)).toBe(agent.key);
    }
  });
});

describe('isSampleAgentName', () => {
  it('agrees with sampleAgentKeyForAgentName (same boundary rule)', () => {
    const names = [
      'email-phishing-demo-agent-9lhh53',
      'calculator-demo-agent-abc123',
      'calculator-demo-agentxyz', // partial token — no separator
      'my-custom-agent',
      '',
    ];
    for (const name of names) {
      expect(isSampleAgentName(name)).toBe(sampleAgentKeyForAgentName(name) !== undefined);
    }
  });

  it('requires the prefix separator', () => {
    expect(isSampleAgentName('calculator-demo-agent-abc123')).toBe(true);
    expect(isSampleAgentName('calculator-demo-agentxyz')).toBe(false);
  });
});
