// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  EVAL_CONFIG_SAMPLES,
  isSampleAgentName,
  SAMPLE_AGENTS,
  sampleAgentKeyForAgentName,
} from '@studio/constants/sampleAgents';

describe('sampleAgentKeyForAgentName', () => {
  it('matches a generated example agent name to its key', () => {
    expect(sampleAgentKeyForAgentName('email-security-analyst-demo-agent-abc123')).toBe(
      'email_security_analyst'
    );
  });

  it('returns undefined for non-example agents and empty input', () => {
    expect(sampleAgentKeyForAgentName('my-custom-agent')).toBeUndefined();
    expect(sampleAgentKeyForAgentName(undefined)).toBeUndefined();
    expect(sampleAgentKeyForAgentName('')).toBeUndefined();
  });

  it('requires the prefix separator (no partial-token match)', () => {
    expect(sampleAgentKeyForAgentName('email-security-analystxyz')).toBeUndefined();
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
      'email-security-analyst-demo-agent-abc123',
      'email-phishingxyz',
      'my-custom-agent',
      '',
    ];
    for (const name of names) {
      expect(isSampleAgentName(name)).toBe(sampleAgentKeyForAgentName(name) !== undefined);
    }
  });

  it('requires the prefix separator', () => {
    expect(isSampleAgentName('email-security-analyst-demo-agent-abc123')).toBe(true);
    expect(isSampleAgentName('email-phishingxyz')).toBe(false);
  });
});

describe('evaluation samples', () => {
  it('offers both paradigms independently of any agent', () => {
    expect(EVAL_CONFIG_SAMPLES.map((sample) => sample.key)).toEqual([
      'task_driven',
      'dataset_driven',
    ]);
  });

  it('gives the dataset-driven config a dataset to seed and the task-driven one none', () => {
    const byKey = Object.fromEntries(EVAL_CONFIG_SAMPLES.map((sample) => [sample.key, sample]));
    expect(byKey.dataset_driven.datasetPath).toBeDefined();
    expect(byKey.task_driven.datasetPath).toBeUndefined();
  });

  it('carries no agent coupling on the config entries', () => {
    for (const sample of EVAL_CONFIG_SAMPLES) {
      expect(Object.keys(sample)).not.toContain('namePrefix');
      expect(Object.keys(sample)).not.toContain('agentConfigPath');
    }
  });
});
