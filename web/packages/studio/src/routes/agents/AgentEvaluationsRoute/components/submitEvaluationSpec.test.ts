// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  bareName,
  buildAgentEvalRequestBody,
  buildAgentTarget,
  buildEvalJobName,
  buildPersistedSpec,
  injectJudgeModel,
  type InlineMetricBundle,
  parseEvalConfig,
  type PersistedEvalSpec,
} from '@studio/routes/agents/AgentEvaluationsRoute/components/submitEvaluationSpec';

const metric: InlineMetricBundle = {
  bundle_kind: 'metric-bundle',
  bundle_format_version: 'v1',
  metric_type: 'llm-judge',
  payload: { kind: 'inline', metric: { type: 'llm-judge', scores: [{ name: 'accuracy' }] } },
};

const config: PersistedEvalSpec = {
  tasks: [
    {
      id: 'A',
      intent: 'classify',
      inputs: { instruction: 'email a' },
      reference: { label: 'phishing' },
      metrics: [metric],
    },
    {
      id: 'B',
      intent: 'classify',
      inputs: { instruction: 'email b' },
      reference: { label: 'benign' },
      metrics: [metric],
    },
  ],
  max_concurrent_tasks: 2,
};

describe('bareName', () => {
  it('strips a workspace prefix', () => {
    expect(bareName('default/my-model')).toBe('my-model');
    expect(bareName('my-model')).toBe('my-model');
  });
});

describe('buildAgentTarget', () => {
  it('targets the non-streaming /generate endpoint of the agent', () => {
    const target = buildAgentTarget('ws-a', 'support-bot');
    expect(target.kind).toBe('agent');
    expect(target.agent.format).toBe('generic');
    expect(target.agent.stream).toBe(false);
    expect(target.agent.response_path).toBe('$.value');
    expect(target.agent.body).toEqual({ input_message: '{{ instruction }}' });
    expect(target.agent.url).toContain('/agents/support-bot/-/generate');
    expect(target.agent.url).not.toContain('/generate/full');
  });
});

describe('injectJudgeModel', () => {
  it('sets the judge ModelRef string without mutating the input', () => {
    const out = injectJudgeModel(metric, 'ws-a/nemotron-super');
    expect(out.payload.metric.model).toBe('ws-a/nemotron-super');
    expect(metric.payload.metric.model).toBeUndefined();
  });
});

describe('buildPersistedSpec', () => {
  it('applies the judge model to every task metric', () => {
    const spec = buildPersistedSpec(config, 'ws-a/judge');
    for (const task of spec.tasks) {
      expect(task.metrics[0].payload.metric.model).toBe('ws-a/judge');
    }
    expect(spec.max_concurrent_tasks).toBe(2);
  });

  it("keeps the config's own model when no judge is supplied", () => {
    const spec = buildPersistedSpec(config, null);
    expect(spec.tasks[0].metrics[0].payload.metric.model).toBeUndefined();
  });

  it('defaults max_concurrent_tasks when omitted', () => {
    expect(buildPersistedSpec({ tasks: config.tasks }, null).max_concurrent_tasks).toBe(1);
  });
});

describe('buildAgentEvalRequestBody', () => {
  const persisted = (): PersistedEvalSpec => buildPersistedSpec(config, 'ws-a/judge');

  it('assembles a {spec:{tasks,target,max_concurrent_tasks}} body and injects the target', () => {
    const body = buildAgentEvalRequestBody(persisted(), {
      workspace: 'ws-a',
      agent: 'ws-a/support-bot',
    });
    expect(body.spec.tasks).toHaveLength(2);
    expect(body.spec.max_concurrent_tasks).toBe(2);
    expect(body.spec.target.agent.name).toBe('support-bot');
    expect(body.spec.tasks[0].metrics[0].metric_type).toBe('llm-judge');
    // Judge is already baked into the persisted spec; submit does not touch it.
    expect(body.spec.tasks[0].metrics[0].payload.metric.model).toBe('ws-a/judge');
  });

  it('sets benchmark and a fileset-prefixed job name when provided', () => {
    const body = buildAgentEvalRequestBody(persisted(), {
      workspace: 'ws-a',
      agent: 'a',
      filesetName: 'wise-blue',
    });
    expect(body.spec.benchmark).toEqual({ eval_config_fileset: 'wise-blue' });
    expect(body.name).toMatch(/^wise-blue-[a-z0-9]{8}$/);
  });

  it('omits benchmark and name when no fileset name is provided', () => {
    const body = buildAgentEvalRequestBody(persisted(), { workspace: 'ws-a', agent: 'a' });
    expect(body.spec.benchmark).toBeUndefined();
    expect(body.name).toBeUndefined();
  });
});

describe('buildEvalJobName', () => {
  it('prefixes with the fileset name and appends a random suffix', () => {
    expect(buildEvalJobName('wise-blue')).toMatch(/^wise-blue-[a-z0-9]{8}$/);
  });

  it('lowercases and preserves valid characters', () => {
    expect(buildEvalJobName('My_Config.v2')).toMatch(/^my_config\.v2-[a-z0-9]{8}$/);
  });

  it('strips leading non-letter characters so the name starts with a letter', () => {
    expect(buildEvalJobName('123-config')).toMatch(/^config-[a-z0-9]{8}$/);
  });

  it('collapses double hyphens and trims edges', () => {
    expect(buildEvalJobName('--a--b--')).toMatch(/^a-b-[a-z0-9]{8}$/);
  });

  it('stays within the 63-character limit', () => {
    expect(buildEvalJobName('a'.repeat(200)).length).toBeLessThanOrEqual(63);
  });
});

describe('parseEvalConfig', () => {
  it('parses a config round-tripped through JSON', () => {
    const parsed = parseEvalConfig(JSON.stringify(config)) as PersistedEvalSpec;
    expect(parsed.tasks).toHaveLength(2);
    expect(parsed.tasks[0].metrics[0].metric_type).toBe('llm-judge');
    expect(parsed.max_concurrent_tasks).toBe(2);
  });

  it('rejects a config with no tasks', () => {
    expect(() => parseEvalConfig(JSON.stringify({ tasks: [] }))).toThrow(/tasks/);
  });

  it('rejects a task with no metrics', () => {
    expect(() =>
      parseEvalConfig(JSON.stringify({ tasks: [{ id: 'A', intent: 'x', metrics: [] }] }))
    ).toThrow(/metrics/);
  });

  it('rejects a task metric missing payload.metric', () => {
    expect(() =>
      parseEvalConfig(
        JSON.stringify({
          tasks: [{ id: 'A', intent: 'x', metrics: [{ metric_type: 'llm-judge' }] }],
        })
      )
    ).toThrow(/payload\.metric/);
  });
});
