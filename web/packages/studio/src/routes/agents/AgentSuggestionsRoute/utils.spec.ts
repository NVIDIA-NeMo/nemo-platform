// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema/ModelEntity';
import type { AgentConfig } from '@studio/components/dataViews/AgentsDataView';
import type {
  AgentListing,
  OptimizationSuggestion,
  SnapshotShape,
} from '@studio/routes/agents/AgentSuggestionsRoute/types';
import {
  agentHasGuardrails,
  analyze,
  CONTENT_SAFETY_MODEL_RE,
  extractBillionParams,
  GUARDRAIL_MODELS,
  parseSuggestions,
  scanForPii,
  serializeSuggestions,
  snapshotAgentNames,
  snapshotModelNames,
  suggestionIdentity,
} from '@studio/routes/agents/AgentSuggestionsRoute/utils';

const llmConfig = (model_name: string, base_url: string): AgentConfig => ({
  llms: { llm: { _type: 'openai', model_name, base_url } },
});

const makeAgent = (name: string, config?: AgentConfig): AgentListing => ({ name, config });

const makeModel = (name: string): ModelEntity => ({ name }) as ModelEntity;

const baseAnalyzeInput = {
  workspace: 'test-ws',
  agents: [] as AgentListing[],
  models: [] as ModelEntity[],
  piiSampleText: '',
  contentSafetyRisk: false,
  prevSnapshot: null as SnapshotShape | null,
};

describe('extractBillionParams', () => {
  it('parses supported billion suffixes and returns null when absent', () => {
    const cases: Array<[string, number | null]> = [
      ['llama-3-1-70b-instruct', 70],
      ['nemotron-3-nano-30b-a3b', 30],
      ['mixtral-8x7b', 7],
      ['mistral-7.5b', 7.5],
      ['Llama-70B-instruct', 70],
      ['gpt-4o-mini', null],
      ['', null],
    ];

    for (const [name, expected] of cases) {
      expect(extractBillionParams(name)).toBe(expected);
    }
  });
});

describe('CONTENT_SAFETY_MODEL_RE', () => {
  it('matches safety classifiers and excludes topic-control/chat models', () => {
    const matching = [
      'nvidia-llama-3-1-nemoguard-8b-content-safety',
      'nvidia-llama-3-1-nemotron-safety-guard-8b-v3',
      'gliner-multi',
    ];
    const nonMatching = [
      'nvidia-llama-3-1-nemoguard-8b-topic-control',
      'llama-3-1-70b-instruct',
      'nvidia-nemotron-mini-4b',
    ];

    for (const name of matching) {
      expect(CONTENT_SAFETY_MODEL_RE.test(name)).toBe(true);
    }
    for (const name of nonMatching) {
      expect(CONTENT_SAFETY_MODEL_RE.test(name)).toBe(false);
    }
  });
});

describe('agentHasGuardrails', () => {
  it('detects guardrails only when every configured LLM routes through /guardrails/', () => {
    const guardedConfig: AgentConfig = {
      llms: {
        a: { _type: 'openai', model_name: 'm', base_url: 'http://x/apis/guardrails/v2/...' },
        b: { _type: 'openai', model_name: 'n', base_url: 'http://x/apis/guardrails/v2/...' },
      },
    };
    const unguardedCases: AgentConfig[] = [
      {
        llms: {
          a: { _type: 'openai', model_name: 'm', base_url: 'http://x/apis/guardrails/v2/...' },
          b: {
            _type: 'openai',
            model_name: 'n',
            base_url: 'http://x/apis/inference-gateway/v2/...',
          },
        },
      },
      {},
      { llms: {} },
      { llms: { a: { _type: 'openai', model_name: 'm' } } },
    ];

    expect(agentHasGuardrails(guardedConfig)).toBe(true);
    for (const config of unguardedCases) {
      expect(agentHasGuardrails(config)).toBe(false);
    }
  });
});

describe('parseSuggestions', () => {
  it('parses one JSON object per non-empty line', () => {
    const text = [
      '{"type":"guardrails","title":"a","detail":"b"}',
      '',
      '{"type":"data_safety","title":"c","detail":"d"}',
    ].join('\n');
    expect(parseSuggestions(text)).toEqual([
      { type: 'guardrails', title: 'a', detail: 'b' },
      { type: 'data_safety', title: 'c', detail: 'd' },
    ]);
  });

  it('skips malformed lines without throwing', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const text = '{"type":"guardrails","title":"a","detail":"b"}\nnot-json\n';
    expect(parseSuggestions(text)).toHaveLength(1);
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});

describe('serializeSuggestions', () => {
  it('round-trips with parseSuggestions', () => {
    const original: OptimizationSuggestion[] = [
      { type: 'guardrails', title: 'a', detail: 'b' },
      { type: 'model_optimization', title: 'c', detail: 'd', agent: 'x', model: 'y' },
    ];
    const out = serializeSuggestions(original);
    expect(parseSuggestions(out)).toEqual(original);
    expect(out.split('\n')).toHaveLength(original.length);
  });
});

describe('scanForPii', () => {
  it('flags supported PII patterns when context confirms them', () => {
    expect(scanForPii('Contact me at jane.doe@company.org for details.')).toContain(
      'email address'
    );
    expect(scanForPii('SSN: 123-45-6789 on file')).toContain('SSN');
    expect(scanForPii('Call me at 415-555-1234 anytime')).toContain('phone number');
    expect(scanForPii('Visa card ending 4111-1111-1111-1111 charged')).toContain('credit card');
  });

  it('rejects common false positives', () => {
    expect(scanForPii('Reach out to user@example.com')).not.toContain('email address');
    expect(scanForPii('mailto link http://noreply@host.com/x')).not.toContain('email address');
    expect(scanForPii('Booking ref 123-45-6789, no other info')).not.toContain('SSN');
    expect(scanForPii('event_ts=1775450116084 user=foo')).not.toContain('phone number');
    expect(scanForPii('id-string 4111-1111-1111-1111 unrelated')).not.toContain('credit card');
    expect(scanForPii('hello world, no PII here')).toEqual([]);
  });

  it('reports each pattern type at most once', () => {
    const text = 'Email a@b.co and c@d.co; SSN 111-22-3333 and SSN 444-55-6666 mentioned.';
    const hits = scanForPii(text);
    expect(hits.filter((h) => h === 'email address')).toHaveLength(1);
    expect(hits.filter((h) => h === 'SSN')).toHaveLength(1);
  });
});

describe('analyze — guardrails', () => {
  it('flags an agent that bypasses guardrails', () => {
    const agents = [
      makeAgent('alpha', llmConfig('llama-70b', 'http://x/apis/inference-gateway/v2/...')),
    ];
    const result = analyze({ ...baseAnalyzeInput, agents });
    const guardrailSuggestion = result.find((s) => s.type === 'guardrails');
    expect(guardrailSuggestion).toBeDefined();
    expect(guardrailSuggestion?.agent).toBe('alpha');
    expect(guardrailSuggestion?.severity).toBe('high');
    expect(guardrailSuggestion?.suggested_actions?.[1]).toContain(GUARDRAIL_MODELS[0]);
  });

  it('does not flag guarded agents or agents with no config', () => {
    const agentSets = [
      [makeAgent('beta', llmConfig('llama-70b', 'http://x/apis/guardrails/v2/...'))],
      [makeAgent('gamma')],
    ];

    for (const agents of agentSets) {
      const result = analyze({ ...baseAnalyzeInput, agents });
      expect(result.some((s) => s.type === 'guardrails')).toBe(false);
    }
  });

  it('shows the unguarded model(s) — not the first configured one — for mixed configs', () => {
    const agents: AgentListing[] = [
      {
        name: 'mixed',
        config: {
          llms: {
            guarded: {
              _type: 'openai',
              model_name: 'guarded-model',
              base_url: 'http://x/apis/guardrails/v2/...',
            },
            risky: {
              _type: 'openai',
              model_name: 'risky-model',
              base_url: 'http://x/apis/inference-gateway/v2/...',
            },
          },
        },
      },
    ];
    const result = analyze({ ...baseAnalyzeInput, agents });
    const g = result.find((s) => s.type === 'guardrails');
    expect(g?.model).toBe('risky-model');
  });

  it('emits one suggestion per unguarded LLM so (type, agent, model) identity is stable', () => {
    const agents: AgentListing[] = [
      {
        name: 'multi-unguarded',
        config: {
          llms: {
            a: {
              _type: 'openai',
              model_name: 'risky-a',
              base_url: 'http://x/apis/inference-gateway/v2/...',
            },
            b: {
              _type: 'openai',
              model_name: 'risky-b',
              base_url: 'http://x/apis/inference-gateway/v2/...',
            },
          },
        },
      },
    ];
    const result = analyze({ ...baseAnalyzeInput, agents });
    const guardrails = result.filter((s) => s.type === 'guardrails');
    expect(guardrails.map((s) => s.model).sort()).toEqual(['risky-a', 'risky-b']);
  });
});

describe('analyze — model optimization', () => {
  it('suggests a smaller model for an agent above the threshold', () => {
    const agents = [
      makeAgent('big', llmConfig('llama-3-1-70b', 'http://x/apis/inference-gateway/v2/...')),
    ];
    const models = [makeModel('llama-3-1-8b'), makeModel('llama-3-1-70b'), makeModel('mistral-7b')];
    const result = analyze({ ...baseAnalyzeInput, agents, models });
    const opt = result.find((s) => s.type === 'model_optimization');
    expect(opt).toBeDefined();
    // `model` is the source (currently-deployed) model — what the badge shows.
    expect(opt?.model).toBe('llama-3-1-70b');
    // Recommended target lives in title + detail.
    expect(opt?.title).toContain('llama-3-1-8b');
    expect(opt?.detail).toContain('llama-3-1-8b');
    expect(opt?.suggested_actions?.[0]).toContain('nemo agents evaluate');
    expect(opt?.suggested_actions?.[1]).toContain('switchyard');
  });

  it('emits a 3-step apply block (create sibling + deploy + evaluate) for model_optimization', () => {
    const agents = [
      makeAgent(
        'support-bot',
        llmConfig('llama-3-1-70b', 'http://x/apis/inference-gateway/v2/...')
      ),
    ];
    const models = [makeModel('llama-3-1-8b'), makeModel('llama-3-1-70b')];
    const result = analyze({ ...baseAnalyzeInput, agents, models, workspace: 'ws-a' });
    const opt = result.find((s) => s.type === 'model_optimization');
    expect(Array.isArray(opt?.apply)).toBe(true);
    const steps = opt?.apply as {
      method: string;
      path: string;
      body: {
        name?: string;
        agent?: string;
        spec?: { agent?: string; eval_config?: string; eval_config_fileset?: string };
      };
    }[];
    expect(steps).toHaveLength(3);
    // Sibling name: <agent>-<model-slug>-<5-char base36 random>. The random
    // suffix isolates re-applies; identity keys off (type, agent, source-model)
    // so dedupe still works across reruns.
    const siblingPattern = /^support-bot-llama-3-1-8b-[a-z0-9]{5}$/;
    expect(steps[0].method).toBe('POST');
    expect(steps[0].path).toBe('/apis/agents/v2/workspaces/ws-a/agents');
    expect(steps[0].body.name).toMatch(siblingPattern);
    const siblingName = steps[0].body.name as string;
    expect(steps[1].method).toBe('POST');
    expect(steps[1].path).toBe('/apis/agents/v2/workspaces/ws-a/deployments');
    // Identity binding: deployment must target the sibling declared in step 1.
    expect(steps[1].body.agent).toBe(siblingName);
    // Step 3: evaluate the sibling using the per-agent eval fileset convention.
    expect(steps[2].method).toBe('POST');
    expect(steps[2].path).toBe('/apis/agents/v2/workspaces/ws-a/jobs/evaluate');
    expect(steps[2].body.spec?.agent).toBe(siblingName);
    expect(steps[2].body.spec?.eval_config_fileset).toBe('support-bot-eval');
    expect(steps[2].body.spec?.eval_config).toBe('react-eval.yml');
    expect(opt?.apply_description).toContain('support-bot-eval');
  });

  it('prefers Nemotron candidates when present', () => {
    const agents = [
      makeAgent('big', llmConfig('llama-70b', 'http://x/apis/inference-gateway/v2/...')),
    ];
    const models = [
      makeModel('llama-3-1-8b'),
      makeModel('nvidia-nemotron-mini-4b'),
      makeModel('mistral-7b'),
    ];
    const result = analyze({ ...baseAnalyzeInput, agents, models });
    const opt = result.find((s) => s.type === 'model_optimization');
    expect(opt?.title).toContain('nvidia-nemotron-mini-4b');
    expect(opt?.detail).toContain('(Nemotron)');
  });

  it('does not suggest when the current model is small or no smaller model exists', () => {
    const cases = [
      {
        agents: [
          makeAgent('small', llmConfig('llama-8b', 'http://x/apis/inference-gateway/v2/...')),
        ],
        models: [makeModel('llama-4b')],
      },
      {
        agents: [
          makeAgent('big', llmConfig('llama-70b', 'http://x/apis/inference-gateway/v2/...')),
        ],
        models: [makeModel('llama-70b'), makeModel('llama-405b')],
      },
    ];

    for (const { agents, models } of cases) {
      const result = analyze({ ...baseAnalyzeInput, agents, models });
      expect(result.some((s) => s.type === 'model_optimization')).toBe(false);
    }
  });

  it('does not recommend safety/guardrail/topic-control models as chat replacements', () => {
    const agents = [
      makeAgent('big', llmConfig('llama-3-1-70b', 'http://x/apis/inference-gateway/v2/...')),
    ];
    const models = [
      makeModel('nvidia-llama-3-1-nemoguard-8b-content-safety'),
      makeModel('nvidia-llama-3-1-nemoguard-8b-topic-control'),
      makeModel('nvidia-llama-3-1-nemotron-safety-guard-8b-v3'),
      makeModel('llama-3-1-8b'),
    ];
    const result = analyze({ ...baseAnalyzeInput, agents, models });
    const opt = result.find((s) => s.type === 'model_optimization');
    expect(opt?.title).toContain('llama-3-1-8b');
    expect(opt?.title).not.toMatch(/nemoguard|safety-guard|topic-control/);
  });

  it('emits one suggestion per oversized LLM in a multi-LLM agent', () => {
    const agents: AgentListing[] = [
      {
        name: 'multi',
        config: {
          llms: {
            router: {
              _type: 'openai',
              model_name: 'llama-3-1-8b',
              base_url: 'http://x/apis/inference-gateway/v2/...',
            },
            worker: {
              _type: 'openai',
              model_name: 'llama-3-1-70b',
              base_url: 'http://x/apis/inference-gateway/v2/...',
            },
            heavy: {
              _type: 'openai',
              model_name: 'llama-3-1-405b',
              base_url: 'http://x/apis/inference-gateway/v2/...',
            },
          },
        },
      },
    ];
    const models = [
      makeModel('llama-3-1-8b'),
      makeModel('llama-3-1-70b'),
      makeModel('llama-3-1-405b'),
    ];
    const result = analyze({ ...baseAnalyzeInput, agents, models });
    const opts = result.filter((s) => s.type === 'model_optimization');
    // 70b → 8b and 405b → 70b. The 8b router is below the threshold.
    expect(opts).toHaveLength(2);
    // Distinct identities so applied-state merge doesn't collapse them.
    expect(new Set(opts.map(suggestionIdentity)).size).toBe(2);
    expect(opts.map((o) => o.model)).toEqual(
      expect.arrayContaining(['llama-3-1-70b', 'llama-3-1-405b'])
    );
  });
});

describe('analyze — data safety', () => {
  it('emits one data-safety suggestion for PII, content risk, or both signals', () => {
    const cases = [
      {
        input: { piiSampleText: 'SSN: 123-45-6789 on file' },
        fragments: ['SSN'],
      },
      {
        input: { contentSafetyRisk: true },
        fragments: ['Content safety model'],
      },
      {
        input: { piiSampleText: 'SSN: 123-45-6789 on file', contentSafetyRisk: true },
        fragments: ['SSN', 'Content safety'],
      },
    ];

    for (const { input, fragments } of cases) {
      const result = analyze({ ...baseAnalyzeInput, ...input });
      const dataSafety = result.filter((s) => s.type === 'data_safety');
      expect(dataSafety).toHaveLength(1);
      for (const fragment of fragments) {
        expect(dataSafety[0]?.detail).toContain(fragment);
      }
    }
  });

  it('emits no suggestion on clean data', () => {
    const result = analyze({
      ...baseAnalyzeInput,
      piiSampleText: 'no pii here at all',
      contentSafetyRisk: false,
    });
    expect(result.some((s) => s.type === 'data_safety')).toBe(false);
  });
});

const makeSnapshot = (modelsByAgent: Record<string, string[]>): SnapshotShape => ({
  agents: Object.fromEntries(
    Object.entries(modelsByAgent).map(([name, modelNames]) => [
      name,
      { modelNames, agentNames: [name], updatedAt: '' },
    ])
  ),
});

describe('analyze — new model scan', () => {
  it('emits one suggestion per new model with per-model actions', () => {
    const result = analyze({
      ...baseAnalyzeInput,
      models: [makeModel('a'), makeModel('b'), makeModel('c'), makeModel('new-model-7b')],
      prevSnapshot: makeSnapshot({ 'agent-1': ['a', 'b'] }),
    });
    const newModels = result.filter((s) => s.type === 'new_model_scan');
    expect(newModels).toHaveLength(2);
    expect(newModels.map((s) => s.model)).toEqual(['c', 'new-model-7b']);
    const newModel = newModels.find((s) => s.model === 'new-model-7b');
    expect(newModel?.model).toBe('new-model-7b');
    expect(newModel?.suggested_actions?.[0]).toContain('nemo auditor targets create');
    expect(newModel?.suggested_actions?.[0]).toContain('"model": "new-model-7b"');
    expect(newModel?.suggested_actions?.[1]).toContain('nemo auditor audit run --spec');
    expect(newModel?.suggested_actions?.[1]).toContain('"target": "default/<target>"');
    expect(newModel?.suggested_actions?.[2]).toContain(
      'nemo evaluation jobs create --model new-model-7b'
    );
  });

  it('does not fire without a previous baseline or when no models are new', () => {
    const cases = [
      null,
      makeSnapshot({ 'agent-1': ['a', 'b', 'c'] }),
    ] satisfies Array<SnapshotShape | null>;

    for (const prevSnapshot of cases) {
      const result = analyze({
        ...baseAnalyzeInput,
        models: [makeModel('a'), makeModel('b')],
        prevSnapshot,
      });
      expect(result.some((s) => s.type === 'new_model_scan')).toBe(false);
    }
  });

  it('unions modelNames across every agent entry in the keyed snapshot', () => {
    const result = analyze({
      ...baseAnalyzeInput,
      models: [makeModel('a'), makeModel('b'), makeModel('c'), makeModel('new-model-7b')],
      prevSnapshot: makeSnapshot({ 'support-bot': ['a'], 'triage-bot': ['b'] }),
    });
    const newModels = result.filter((s) => s.type === 'new_model_scan');
    expect(newModels.map((s) => s.model)).toEqual(['c', 'new-model-7b']);
  });
});

describe('snapshotModelNames / snapshotAgentNames', () => {
  it('returns empty for null', () => {
    expect(snapshotModelNames(null)).toEqual([]);
    expect(snapshotAgentNames(null)).toEqual([]);
  });

  it('aggregates across the keyed shape and dedupes shared models', () => {
    const snapshot = makeSnapshot({ 'agent-1': ['a', 'b'], 'agent-2': ['b', 'c'] });
    expect(snapshotModelNames(snapshot).sort()).toEqual(['a', 'b', 'c']);
    expect(snapshotAgentNames(snapshot).sort()).toEqual(['agent-1', 'agent-2']);
  });
});
