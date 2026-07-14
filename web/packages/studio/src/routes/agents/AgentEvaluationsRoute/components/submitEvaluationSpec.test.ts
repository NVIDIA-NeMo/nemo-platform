// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SAMPLE_AGENTS } from '@studio/constants/sampleAgents';
import {
  buildSubmitSpec,
  CREATE_NEW,
  evalOutputDescription,
  evaluateRequestBody,
  generateOutputFilesetName,
} from '@studio/routes/agents/AgentEvaluationsRoute/components/submitEvaluationSpec';

const baseForm = {
  agent: 'my-agent',
  evalConfig: CREATE_NEW,
  newName: '',
  mode: 'default' as const,
  exampleKey: SAMPLE_AGENTS[0].key,
  datasetFile: null as string | null,
};

describe('buildSubmitSpec', () => {
  it('reuses an existing eval config untouched (no seed sources)', () => {
    const existing = new Map([['wise-pretzel', 'analyzer-eval.yml']]);
    const spec = buildSubmitSpec({ ...baseForm, evalConfig: 'wise-pretzel' }, existing);

    expect(spec).toEqual({
      agent: 'my-agent',
      evalConfig: 'analyzer-eval.yml',
      evalConfigFileset: 'wise-pretzel',
    });
    expect(spec.seedSources).toBeUndefined();
  });

  it('creates a new slug fileset and seeds the example config + dataset', () => {
    const spec = buildSubmitSpec(
      { ...baseForm, evalConfig: CREATE_NEW, mode: 'default', newName: '  wise-pretzel  ' },
      new Map()
    );

    // Trimmed slug becomes the eval-config fileset (also the output target).
    expect(spec.evalConfigFileset).toBe('wise-pretzel');
    expect(spec.evalConfig.startsWith(`${SAMPLE_AGENTS[0].key}-`)).toBe(true);
    expect(spec.seedSources).toHaveLength(2);
  });

  it("reuses the picked file's own fileset when creating from a fileset YAML", () => {
    const spec = buildSubmitSpec(
      {
        ...baseForm,
        evalConfig: CREATE_NEW,
        mode: 'fileset',
        datasetFile: 'default/my-fs#eval.yml',
      },
      new Map()
    );

    expect(spec.evalConfigFileset).toBe('my-fs');
    expect(spec.evalConfig).toBe('eval.yml');
    expect(spec.seedSources).toBeUndefined();
  });
});

describe('generateOutputFilesetName', () => {
  it('mints a fresh per-run <agent>-eval-out-<random> name', () => {
    const a = generateOutputFilesetName('my-agent');
    const b = generateOutputFilesetName('my-agent');
    expect(a).toMatch(/^my-agent-eval-out-[a-z0-9]{5}$/);
    expect(a).not.toBe(b); // random suffix differs per call
  });
});

describe('evalOutputDescription', () => {
  it('describes the agent and eval-config fileset', () => {
    expect(
      evalOutputDescription({
        agent: 'my-agent',
        evalConfig: 'eval.yml',
        evalConfigFileset: 'wise-pretzel',
      })
    ).toBe('Agent Evaluation output, agent: my-agent, config: wise-pretzel');
  });
});

describe('evaluateRequestBody', () => {
  it('sends the chosen eval-config fileset and the given per-run output fileset', () => {
    const body = evaluateRequestBody(
      { agent: 'my-agent', evalConfig: 'eval.yml', evalConfigFileset: 'wise-pretzel' },
      'my-agent-eval-out-ab3d9'
    );

    expect(body.spec.eval_config).toBe('eval.yml');
    expect(body.spec.eval_config_fileset).toBe('wise-pretzel');
    // Output is a distinct per-run fileset, not the config fileset.
    expect(body.spec.output).toBe('my-agent-eval-out-ab3d9');
    expect(body.spec.output).not.toBe(body.spec.eval_config_fileset);
  });
});
