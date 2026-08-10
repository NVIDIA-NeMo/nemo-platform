// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SAMPLE_AGENTS, getSampleAgent, isSampleAgentName } from '@studio/constants/sampleAgents';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import YAML from 'yaml';

const REPO_ROOT = join(__dirname, '../../../../..');
const PUBLIC_DIR = join(REPO_ROOT, 'web/packages/studio/public');
const PLUGIN_EXAMPLES = join(REPO_ROOT, 'plugins/nemo-agents/examples/nemo-agent-config');

describe('SAMPLE_AGENTS', () => {
  it.each(SAMPLE_AGENTS)('$key ships the asset it points at', (sample) => {
    const text = readFileSync(join(PUBLIC_DIR, sample.agentConfigPath), 'utf8');
    const config = YAML.parse(text) as Record<string, unknown>;

    expect(config.config_format).toBe(sample.configFormat ?? 'nat-workflow-v1');
  });

  it('the Fabric sample exposes the model slot loadSampleAgentConfig writes to', () => {
    const sample = getSampleAgent('email_phishing_agent');
    const text = readFileSync(join(PUBLIC_DIR, sample.agentConfigPath), 'utf8');
    const config = YAML.parse(text) as { models?: { default?: { model?: string } } };

    expect(sample.configFormat).toBe('nemo-agents-spec-v1');
    expect(config.models?.default).toBeDefined();
  });

  it('the shipped asset stays identical to the plugin example it was copied from', () => {
    const shipped = readFileSync(
      join(PUBLIC_DIR, 'sample-agents/email-phishing-agent/agent.yaml'),
      'utf8'
    );
    const source = readFileSync(join(PLUGIN_EXAMPLES, 'email-phishing-agent/agent.yaml'), 'utf8');

    expect(shipped).toBe(source);
  });

  it('recognises a generated sample name', () => {
    expect(isSampleAgentName('email-phishing-agent-a1b2c3')).toBe(true);
    expect(isSampleAgentName('my-own-agent')).toBe(false);
  });
});
