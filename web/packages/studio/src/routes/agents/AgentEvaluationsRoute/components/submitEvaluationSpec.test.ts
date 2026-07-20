// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  bareName,
  buildAgentEvalRequestBody,
  buildAgentTarget,
  type EvalConfig,
  fanMetricOntoTasks,
  injectJudgeModel,
  type InlineMetricBundle,
  parseEvalConfig,
} from '@studio/routes/agents/AgentEvaluationsRoute/components/submitEvaluationSpec';

/** A config whose metric already carries a baked-in judge ModelRef. */
const configWithBakedJudge = (): EvalConfig => ({
  ...config,
  metric: {
    ...metric,
    payload: { kind: 'inline', metric: { ...metric.payload.metric, model: 'ws-a/baked-in' } },
  },
});

const metric: InlineMetricBundle = {
  bundle_kind: 'metric-bundle',
  bundle_format_version: 'v1',
  metric_type: 'llm-judge',
  payload: { kind: 'inline', metric: { type: 'llm-judge', scores: [{ name: 'accuracy' }] } },
};

const config: EvalConfig = {
  tasks: [
    {
      id: 'A',
      intent: 'classify',
      inputs: { instruction: 'email a' },
      reference: { label: 'phishing' },
    },
    {
      id: 'B',
      intent: 'classify',
      inputs: { instruction: 'email b' },
      reference: { label: 'benign' },
    },
  ],
  metric,
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

describe('fanMetricOntoTasks', () => {
  it('attaches the judge-injected metric to every task', () => {
    const tasks = fanMetricOntoTasks(config, 'ws-a/j');
    expect(tasks).toHaveLength(2);
    for (const t of tasks) {
      expect(t.metrics).toHaveLength(1);
      expect(t.metrics[0].payload.metric.model).toBe('ws-a/j');
    }
  });

  it("keeps the config's own judge when none is supplied", () => {
    const tasks = fanMetricOntoTasks(configWithBakedJudge(), null);
    expect(tasks[0].metrics[0].payload.metric.model).toBe('ws-a/baked-in');
  });
});

describe('buildAgentEvalRequestBody', () => {
  it('assembles a {spec:{tasks,target,max_concurrent_tasks}} body', () => {
    const body = buildAgentEvalRequestBody(config, {
      workspace: 'ws-a',
      agent: 'ws-a/support-bot',
      judgeModel: 'ws-a/judge',
    });
    expect(body.spec.tasks).toHaveLength(2);
    expect(body.spec.max_concurrent_tasks).toBe(2);
    expect(body.spec.target.agent.name).toBe('support-bot');
    expect(body.spec.tasks[0].metrics[0].metric_type).toBe('llm-judge');
    expect(body.spec.tasks[0].metrics[0].payload.metric.model).toBe('ws-a/judge');
  });

  it("keeps the config's baked-in judge when no judge is selected (chosen fileset)", () => {
    const body = buildAgentEvalRequestBody(configWithBakedJudge(), {
      workspace: 'ws-a',
      agent: 'a',
      judgeModel: '',
    });
    expect(body.spec.tasks[0].metrics[0].payload.metric.model).toBe('ws-a/baked-in');
  });

  it('defaults max_concurrent_tasks when the config omits it', () => {
    const body = buildAgentEvalRequestBody(
      { tasks: config.tasks, metric },
      { workspace: 'ws-a', agent: 'a', judgeModel: 'ws-a/j' }
    );
    expect(body.spec.max_concurrent_tasks).toBe(1);
  });
});

describe('parseEvalConfig', () => {
  it('parses a valid config', () => {
    const parsed = parseEvalConfig(JSON.stringify(config));
    expect(parsed.tasks).toHaveLength(2);
    expect(parsed.metric.metric_type).toBe('llm-judge');
  });

  it('rejects a config with no tasks', () => {
    expect(() => parseEvalConfig(JSON.stringify({ tasks: [], metric }))).toThrow(/tasks/);
  });

  it('rejects a config with no metric', () => {
    expect(() => parseEvalConfig(JSON.stringify({ tasks: config.tasks }))).toThrow(/metric/);
  });

  it('rejects a metric missing payload.metric', () => {
    expect(() =>
      parseEvalConfig(JSON.stringify({ tasks: config.tasks, metric: { metric_type: 'llm-judge' } }))
    ).toThrow(/payload\.metric/);
  });
});
