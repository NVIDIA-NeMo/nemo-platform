// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  bareName,
  buildAgentEvalRequestBody,
  buildAgentTarget,
  buildJudgeModel,
  type EvalConfig,
  fanMetricOntoTasks,
  injectJudgeModel,
  type InlineMetricBundle,
  parseEvalConfig,
} from '@studio/routes/agents/AgentEvaluationsRoute/components/submitEvaluationSpec';

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

describe('buildJudgeModel', () => {
  it('builds an IGW openai endpoint with the bare model name + nim format', () => {
    const judge = buildJudgeModel('ws-a', 'ws-a/nemotron-super');
    expect(judge.name).toBe('nemotron-super');
    expect(judge.format).toBe('nim');
    expect(judge.url).toContain('/apis/inference-gateway/v2/workspaces/ws-a/openai/-/v1');
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
  it('injects the judge model without mutating the input', () => {
    const judge = buildJudgeModel('ws-a', 'ws-a/j');
    const out = injectJudgeModel(metric, judge);
    expect(out.payload.metric.model).toEqual(judge);
    expect(metric.payload.metric.model).toBeUndefined();
  });
});

describe('fanMetricOntoTasks', () => {
  it('attaches the judge-injected metric to every task', () => {
    const judge = buildJudgeModel('ws-a', 'ws-a/j');
    const tasks = fanMetricOntoTasks(config, judge);
    expect(tasks).toHaveLength(2);
    for (const t of tasks) {
      expect(t.metrics).toHaveLength(1);
      expect((t.metrics[0].payload.metric.model as { name: string }).name).toBe('j');
    }
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
});
