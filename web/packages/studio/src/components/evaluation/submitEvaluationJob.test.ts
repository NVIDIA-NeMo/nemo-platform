// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  applyDatasetEvalOverrides,
  bareName,
  buildAgentEvalRequestBody,
  buildAgentTarget,
  buildDatasetAgentTarget,
  buildDatasetEvalRequestBody,
  type DatasetEvalSpec,
  datasetEvalConfigError,
  buildEvalJobName,
  buildPersistedSpec,
  injectJudgeModel,
  type InlineMetricBundle,
  isDatasetEvalSpec,
  parseEvalConfig,
  type PersistedEvalSpec,
} from '@studio/components/evaluation/submitEvaluationJob';

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
  it('targets the non-streaming chat-completions endpoint of the agent', () => {
    const target = buildAgentTarget('ws-a', 'support-bot');
    expect(target.kind).toBe('agent');
    expect(target.agent.format).toBe('generic');
    expect(target.agent.stream).toBe(false);
    expect(target.agent.response_path).toBe('$.choices[0].message.content');
    expect(target.agent.body).toEqual({
      model: 'support-bot',
      messages: [{ role: 'user', content: '{{ instruction }}' }],
      stream: false,
    });
    expect(target.agent.url).toContain('/agents/support-bot/-/v1/chat/completions');
  });

  it('strips a workspace prefix from the agent name', () => {
    const target = buildAgentTarget('ws-a', 'ws-a/support-bot');
    expect(target.agent.name).toBe('support-bot');
    expect(target.agent.body.model).toBe('support-bot');
    expect(target.agent.url).toContain('/agents/support-bot/-/');
  });
});

describe('buildDatasetAgentTarget', () => {
  it('renders the row prompt into the chat message', () => {
    const target = buildDatasetAgentTarget('ws-a', 'support-bot');
    expect(target.format).toBe('generic');
    expect(target.response_path).toBe('$.choices[0].message.content');
    expect(target.body).toEqual({
      model: 'support-bot',
      messages: [{ role: 'user', content: '{{ prompt }}' }],
      stream: false,
    });
    expect(target.url).toContain('/agents/support-bot/-/v1/chat/completions');
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

  it('sets labels and a fileset-prefixed job name when provided', () => {
    const body = buildAgentEvalRequestBody(persisted(), {
      workspace: 'ws-a',
      agent: 'a',
      filesetName: 'wise-blue',
    });
    expect(body.spec.labels).toEqual({ eval_config_fileset: 'wise-blue' });
    expect(body.name).toMatch(/^wise-blue-[a-z0-9]{8}$/);
  });

  it('omits labels and name when no fileset name is provided', () => {
    const body = buildAgentEvalRequestBody(persisted(), { workspace: 'ws-a', agent: 'a' });
    expect(body.spec.labels).toBeUndefined();
    expect(body.name).toBeUndefined();
  });

  it('names the job after the experiment, falling back to the fileset', () => {
    const withExperiment = buildAgentEvalRequestBody(persisted(), {
      workspace: 'ws-a',
      agent: 'a',
      filesetName: 'wise-blue-data',
      experimentName: 'wise-blue',
    });
    expect(withExperiment.name).toMatch(/^wise-blue-[a-z0-9]{8}$/);

    const filesetOnly = buildAgentEvalRequestBody(persisted(), {
      workspace: 'ws-a',
      agent: 'a',
      filesetName: 'wise-blue-data',
    });
    expect(filesetOnly.name).toMatch(/^wise-blue-data-[a-z0-9]{8}$/);
  });

  it('publishes to the named evaluation when one is selected', () => {
    const body = buildAgentEvalRequestBody(persisted(), {
      workspace: 'ws-a',
      agent: 'a',
      evaluationId: 'nightly-eval-a3f2',
    });
    // agent_name is omitted deliberately: the backend derives it from the agent target.
    expect(body.spec.publication).toEqual({ intake: { evaluation_id: 'nightly-eval-a3f2' } });
  });

  it('omits publication entirely when no evaluation is selected', () => {
    const body = buildAgentEvalRequestBody(persisted(), { workspace: 'ws-a', agent: 'a' });
    expect(body.spec.publication).toBeUndefined();
    expect('publication' in body.spec).toBe(false);
  });
});

describe('buildDatasetEvalRequestBody', () => {
  const datasetConfig: DatasetEvalSpec = {
    dataset: [{ prompt: '2+2?' }],
    metrics: [metric],
    prompt_template: '{{item.prompt}}',
  };

  it('carries publication through the dataset path too, and omits it otherwise', () => {
    const withPublication = buildDatasetEvalRequestBody(
      datasetConfig,
      { workspace: 'ws-a', agent: 'a', evaluationId: 'eval-1' },
      null
    );
    expect(withPublication.spec.publication).toEqual({ intake: { evaluation_id: 'eval-1' } });

    const without = buildDatasetEvalRequestBody(
      datasetConfig,
      { workspace: 'ws-a', agent: 'a' },
      null
    );
    expect(without.spec.publication).toBeUndefined();
  });

  it('forwards authored keys Studio has no opinion about', () => {
    const body = buildDatasetEvalRequestBody(
      { ...datasetConfig, field_mapping: { input: 'question', reference: 'gold' } },
      { workspace: 'ws-a', agent: 'a' },
      null
    );
    expect(body.spec.field_mapping).toEqual({ input: 'question', reference: 'gold' });
    expect(body.spec.dataset).toEqual([{ prompt: '2+2?' }]);
    expect(body.spec.prompt_template).toBe('{{item.prompt}}');
  });

  it('overrides target and params the config authored, rather than forwarding them', () => {
    const body = buildDatasetEvalRequestBody(
      {
        ...datasetConfig,
        target: { kind: 'model', model: 'someone-elses-model' },
        params: { parallelism: 99 },
        publication: { intake: { evaluation_id: 'stale' } },
      },
      { workspace: 'ws-a', agent: 'support-bot', evaluationId: 'eval-1' },
      null
    );
    expect(body.spec.target).toEqual(buildDatasetAgentTarget('ws-a', 'support-bot'));
    expect(body.spec.params).toEqual({
      parallelism: 1,
      request_timeout: 300,
      max_retries: 3,
      ignore_request_failure: true,
    });
    expect(body.spec.publication).toEqual({ intake: { evaluation_id: 'eval-1' } });
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

  const datasetYaml = `
dataset: ws-a/data#rows.jsonl
prompt_template: |-
  Is this legit?
  {{ item.body }}
metrics:
  - bundle_kind: metric-bundle
    bundle_format_version: v1
    metric_type: llm-judge
    payload:
      kind: inline
      metric:
        type: llm-judge
        scores:
          - name: accuracy
`;

  it('parses a dataset-driven config authored as YAML', () => {
    const parsed = parseEvalConfig(datasetYaml, 'eval.yaml') as DatasetEvalSpec;
    expect(isDatasetEvalSpec(parsed)).toBe(true);
    expect(parsed.dataset).toBe('ws-a/data#rows.jsonl');
    expect(parsed.prompt_template).toBe('Is this legit?\n{{ item.body }}');
    expect(parsed.metrics[0].metric_type).toBe('llm-judge');
  });

  it('parses YAML with no filename to sniff from', () => {
    expect((parseEvalConfig(datasetYaml) as DatasetEvalSpec).dataset).toBe('ws-a/data#rows.jsonl');
  });

  it('keeps top-level keys it does not recognize instead of dropping them', () => {
    const parsed = parseEvalConfig(
      JSON.stringify({ ...(parseEvalConfig(datasetYaml) as object), field_mapping: { input: 'q' } })
    ) as DatasetEvalSpec;
    expect(parsed.field_mapping).toEqual({ input: 'q' });
  });

  it('accepts a dataset-driven config with no dataset or prompt_template', () => {
    const parsed = parseEvalConfig(JSON.stringify({ metrics: [metric] })) as DatasetEvalSpec;
    expect(isDatasetEvalSpec(parsed)).toBe(true);
    expect(parsed.dataset).toBeUndefined();
    expect(parsed.prompt_template).toBeUndefined();
  });

  it('rejects a dataset-driven config with no metrics', () => {
    expect(() => parseEvalConfig(JSON.stringify({ dataset: 'a/b#c.jsonl' }))).toThrow(/metrics/);
  });

  it('reports the filename when the text parses as neither JSON nor YAML', () => {
    expect(() => parseEvalConfig('{ nope: [', 'broken.yaml')).toThrow(/"broken\.yaml"/);
  });

  it('rejects a non-object document', () => {
    expect(() => parseEvalConfig('- a\n- b', 'list.yaml')).toThrow(/top-level object/);
  });
});

describe('applyDatasetEvalOverrides', () => {
  const authored: DatasetEvalSpec = {
    dataset: 'ws-a/authored#rows.jsonl',
    prompt_template: '{{ item.authored }}',
    metrics: [metric],
  };

  it('leaves a complete config untouched when every override is blank', () => {
    const out = applyDatasetEvalOverrides(authored, {
      dataset: undefined,
      promptTemplate: '',
      judgeModel: null,
    });
    expect(out.dataset).toBe('ws-a/authored#rows.jsonl');
    expect(out.prompt_template).toBe('{{ item.authored }}');
    expect(out.metrics[0].payload.metric.model).toBeUndefined();
  });

  it('replaces dataset, prompt template and judge model when supplied', () => {
    const out = applyDatasetEvalOverrides(authored, {
      dataset: 'ws-a/uploaded#new.jsonl',
      promptTemplate: '{{ item.override }}',
      judgeModel: 'ws-a/judge',
    });
    expect(out.dataset).toBe('ws-a/uploaded#new.jsonl');
    expect(out.prompt_template).toBe('{{ item.override }}');
    expect(out.metrics[0].payload.metric.model).toBe('ws-a/judge');
  });

  it('fills in a config that authored neither dataset nor prompt template', () => {
    const out = applyDatasetEvalOverrides(
      { metrics: [metric] },
      { dataset: 'ws-a/up#d.jsonl', promptTemplate: '{{ item.q }}' }
    );
    expect(datasetEvalConfigError(out)).toBeNull();
  });

  it('treats a whitespace-only prompt template as unset', () => {
    expect(applyDatasetEvalOverrides(authored, { promptTemplate: '   ' }).prompt_template).toBe(
      '{{ item.authored }}'
    );
  });
});

describe('datasetEvalConfigError', () => {
  it('names the missing dataset', () => {
    expect(datasetEvalConfigError({ metrics: [metric], prompt_template: 'x' })).toMatch(/dataset/);
  });

  it('treats an empty inline dataset and a blank ref as missing', () => {
    expect(datasetEvalConfigError({ metrics: [metric], dataset: [] })).toMatch(/dataset/);
    expect(datasetEvalConfigError({ metrics: [metric], dataset: '  ' })).toMatch(/dataset/);
  });

  it('names the missing prompt template once a dataset is present', () => {
    expect(datasetEvalConfigError({ metrics: [metric], dataset: 'a/b#c.jsonl' })).toMatch(
      /prompt template/
    );
  });

  it('passes a complete config', () => {
    expect(
      datasetEvalConfigError({ metrics: [metric], dataset: 'a/b#c.jsonl', prompt_template: 'x' })
    ).toBeNull();
  });
});
