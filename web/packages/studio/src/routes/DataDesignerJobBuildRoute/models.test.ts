// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import type { ModelProvider } from '@nemo/sdk/generated/platform/schema';
import { DEFAULT_MAX_PARALLEL_REQUESTS } from '@studio/constants/constants';
import {
  type BuilderModel,
  buildModelConfigs,
  buildModelsFromConfig,
  buildModelsFromTemplate,
  buildServedModelNames,
  builderModelFromSelection,
  defaultModelAlias,
  findWorkspaceModel,
  firstAvailableModel,
  modelIdForModel,
  providerForSelection,
  resolveTemplateModel,
  validateModelAlias,
  validateModels,
} from '@studio/routes/DataDesignerJobBuildRoute/models';

const model = (overrides: Partial<BuilderModel> = {}): BuilderModel => ({
  id: 'model-0',
  alias: 'default',
  model: 'nvidia/llama-3.3-nemotron-super-49b-v1',
  provider: 'nvidia',
  inferenceParams: {},
  ...overrides,
});

describe('defaultModelAlias', () => {
  it('returns the first unused model_N alias', () => {
    expect(defaultModelAlias(new Set())).toBe('model_1');
    expect(defaultModelAlias(new Set(['model_1', 'model_2']))).toBe('model_3');
  });
});

describe('model resolution', () => {
  const groups = [
    {
      workspace: 'steramae',
      models: [
        { workspace: 'steramae', name: 'nemotron-oss', model_providers: ['steramae/build'] },
        {
          workspace: 'steramae',
          name: 'nvidia-llama-3-3-nemotron-super-49b-v1-5',
          model_providers: ['steramae/build'],
        },
        { workspace: 'steramae', name: 'no-provider' },
      ],
    },
  ] as unknown as ModelWorkspaceGroup[];

  it('providerForSelection returns the picked entity’s first provider ref', () => {
    expect(
      providerForSelection({ model: 'steramae/nemotron-oss', entity: groups[0].models[0] })
    ).toBe('steramae/build');
  });

  it('providerForSelection returns empty string without an entity or provider', () => {
    expect(
      providerForSelection({ model: 'steramae/no-provider', entity: groups[0].models[2] })
    ).toBe('');
    expect(providerForSelection({ model: 'steramae/unknown' })).toBe('');
  });

  it('firstAvailableModel picks the first model and its provider', () => {
    expect(firstAvailableModel(groups)).toEqual({
      model: 'steramae/nemotron-oss',
      provider: 'steramae/build',
    });
    expect(firstAvailableModel([])).toBeNull();
  });

  it('findWorkspaceModel matches a bare name across workspaces', () => {
    expect(findWorkspaceModel(groups, 'nvidia-llama-3-3-nemotron-super-49b-v1-5')).toEqual({
      model: 'steramae/nvidia-llama-3-3-nemotron-super-49b-v1-5',
      provider: 'steramae/build',
    });
  });

  it('findWorkspaceModel matches a full URN too', () => {
    expect(findWorkspaceModel(groups, 'steramae/nemotron-oss')).toEqual({
      model: 'steramae/nemotron-oss',
      provider: 'steramae/build',
    });
  });

  it('findWorkspaceModel returns null rather than substituting', () => {
    expect(findWorkspaceModel(groups, 'not-in-workspace')).toBeNull();
    expect(findWorkspaceModel([], 'anything')).toBeNull();
  });

  it('resolveTemplateModel falls back to the first model when the preferred is absent', () => {
    expect(resolveTemplateModel(groups, 'not-in-workspace')).toEqual({
      model: 'steramae/nemotron-oss',
      provider: 'steramae/build',
    });
    expect(resolveTemplateModel([], 'anything')).toBeNull();
  });
});

describe('buildServedModelNames / modelIdForModel', () => {
  const providers = [
    {
      workspace: 'steramae',
      name: 'build',
      served_models: [
        {
          model_entity_id: 'steramae/nvidia-llama-3-3-nemotron-super-49b-v1-5',
          served_model_name: 'nvidia/llama-3.3-nemotron-super-49b-v1.5',
        },
        { model_entity_id: 'steramae/nemotron-oss', served_model_name: 'nvidia/nemotron-oss-120b' },
      ],
    },
    {
      // A second provider re-serving the same entity: the first mapping wins.
      workspace: 'steramae',
      name: 'other',
      served_models: [
        {
          model_entity_id: 'steramae/nvidia-llama-3-3-nemotron-super-49b-v1-5',
          served_model_name: 'ignored/duplicate',
        },
      ],
    },
  ] as unknown as ModelProvider[];

  it('maps each served model_entity_id (URN) to its served_model_name, first mapping winning', () => {
    const names = buildServedModelNames(providers);
    expect(names.get('steramae/nvidia-llama-3-3-nemotron-super-49b-v1-5')).toBe(
      'nvidia/llama-3.3-nemotron-super-49b-v1.5'
    );
    expect(names.get('steramae/nemotron-oss')).toBe('nvidia/nemotron-oss-120b');
  });

  it('modelIdForModel resolves the URN to the served model name', () => {
    const names = buildServedModelNames(providers);
    expect(names.size).toBe(2);
    expect(modelIdForModel(names, 'steramae/nvidia-llama-3-3-nemotron-super-49b-v1-5')).toBe(
      'nvidia/llama-3.3-nemotron-super-49b-v1.5'
    );
  });

  it('modelIdForModel falls back to the URN when no mapping is found', () => {
    expect(modelIdForModel(new Map(), 'steramae/unknown')).toBe('steramae/unknown');
  });
});

describe('buildModelsFromTemplate', () => {
  it('seeds models with sequential ids, leaving model/provider empty for auto-fill', () => {
    const models = buildModelsFromTemplate([{ alias: 'default' }], 2);
    expect(models).toEqual([
      {
        id: 'model-2',
        alias: 'default',
        model: '',
        provider: '',
        inferenceParams: {
          temperature: 0.7,
          top_p: 0.9,
          max_parallel_requests: DEFAULT_MAX_PARALLEL_REQUESTS,
        },
      },
    ]);
  });

  it('carries a preferred model through and lets a spec override a sampling default', () => {
    const models = buildModelsFromTemplate([
      { alias: 'judge', model: 'nvidia/gpt-oss', inferenceParams: { temperature: 0 } },
    ]);
    expect(models[0]).toMatchObject({
      alias: 'judge',
      model: 'nvidia/gpt-oss',
      // Explicit temperature wins; top_p still gets the default that truncates the tail.
      inferenceParams: { temperature: 0, top_p: 0.9 },
    });
  });

  it('gives embedding specs a concurrency cap but no chat sampling params', () => {
    const models = buildModelsFromTemplate([
      { alias: 'embedder', inferenceParams: { generation_type: 'embedding' } },
    ]);
    expect(models[0].inferenceParams).toEqual({
      generation_type: 'embedding',
      max_parallel_requests: DEFAULT_MAX_PARALLEL_REQUESTS,
    });
  });

  it('returns an empty array when no specs are given', () => {
    expect(buildModelsFromTemplate()).toEqual([]);
  });
});

describe('builderModelFromSelection', () => {
  it('seeds the model and provider from the selection with a unique default alias', () => {
    expect(
      builderModelFromSelection(
        'model-5',
        { model: 'nvidia/llama-3.3-nemotron-super-49b-v1' },
        'default/nvidia-build',
        new Set(['model_1'])
      )
    ).toEqual({
      id: 'model-5',
      alias: 'model_2',
      model: 'nvidia/llama-3.3-nemotron-super-49b-v1',
      provider: 'default/nvidia-build',
      inferenceParams: {},
    });
  });
});

describe('validateModelAlias', () => {
  it('requires a non-empty, unique alias', () => {
    expect(validateModelAlias('  ', new Set())).toMatch(/required/);
    expect(validateModelAlias('a', new Set(['a']))).toMatch(/already exists/);
    expect(validateModelAlias('a', new Set(['b']))).toBeNull();
  });
});

describe('validateModels', () => {
  it('accepts a fully-specified model', () => {
    expect(
      validateModels([
        model({ inferenceParams: { temperature: 0.7, top_p: 0.9, max_tokens: 512 } }),
      ])
    ).toEqual([]);
  });

  it('flags a model with no selection', () => {
    expect(validateModels([model({ model: '' })])).toContainEqual(
      expect.stringContaining('A model must be selected')
    );
  });

  it('flags duplicate aliases across models', () => {
    const errors = validateModels([
      model({ id: 'model-0', alias: 'dupe' }),
      model({ id: 'model-1', alias: 'dupe' }),
    ]);
    expect(errors.filter((e) => e.includes('already exists'))).toHaveLength(2);
  });
});

describe('buildModelsFromConfig', () => {
  it('reverses chat-completion model configs, numbering ids from startId', () => {
    const configs = buildModelConfigs([
      model({ alias: 'gen', inferenceParams: { temperature: 0.7, top_p: 0.9, max_tokens: 512 } }),
    ]);

    expect(buildModelsFromConfig(configs, 2)).toEqual([
      {
        id: 'model-2',
        alias: 'gen',
        model: 'nvidia/llama-3.3-nemotron-super-49b-v1',
        provider: 'nvidia',
        inferenceParams: {
          generation_type: 'chat-completion',
          temperature: 0.7,
          top_p: 0.9,
          max_tokens: 512,
        },
      },
    ]);
  });

  it('preserves embedding params so a config round-trips unchanged', () => {
    const models = [
      model({
        id: 'model-0',
        alias: 'embedder',
        model: 'nvidia/nv-embedqa-e5-v5',
        provider: 'steramae/build',
        inferenceParams: {
          generation_type: 'embedding',
          encoding_format: 'float',
          extra_body: { input_type: 'query' },
        },
      }),
    ];
    const configs = buildModelConfigs(models);

    expect(buildModelConfigs(buildModelsFromConfig(configs))).toEqual(configs);
  });

  it('returns an empty array for an absent model_configs list', () => {
    expect(buildModelsFromConfig()).toEqual([]);
  });
});

describe('buildModelConfigs', () => {
  it('returns undefined when there are no models', () => {
    expect(buildModelConfigs([])).toBeUndefined();
  });

  it('omits empty optional fields but always includes inference parameters with defaults', () => {
    expect(buildModelConfigs([model({ provider: '' })])).toEqual([
      {
        alias: 'default',
        model: 'nvidia/llama-3.3-nemotron-super-49b-v1',
        provider: '',
        inference_parameters: {
          generation_type: 'chat-completion',
          max_tokens: 1024,
        },
      },
    ]);
  });

  it('forwards max_parallel_requests so the job caps its own fan-out', () => {
    const [config] = buildModelConfigs([model({ inferenceParams: { max_parallel_requests: 4 } })])!;
    expect(config.inference_parameters).toMatchObject({
      generation_type: 'chat-completion',
      max_parallel_requests: 4,
    });
  });

  it('forwards extra_body so backend flags like a thinking-mode switch survive', () => {
    const extra_body = { chat_template_kwargs: { thinking: false } };
    const configs = buildModelConfigs([model({ inferenceParams: { extra_body } })])!;
    expect(configs[0].inference_parameters).toMatchObject({ extra_body });
    // And survives a clone round-trip.
    expect(buildModelsFromConfig(configs)[0].inferenceParams).toMatchObject({ extra_body });
  });

  it('omits max_parallel_requests when no cap was set', () => {
    const [config] = buildModelConfigs([model({ inferenceParams: {} })])!;
    expect(config.inference_parameters).not.toHaveProperty('max_parallel_requests');
  });

  it('round-trips max_parallel_requests back into the builder when cloning', () => {
    const configs = buildModelConfigs([model({ inferenceParams: { max_parallel_requests: 8 } })])!;
    expect(buildModelsFromConfig(configs)[0].inferenceParams).toMatchObject({
      max_parallel_requests: 8,
    });
  });

  it('resolves the model URN to the provider-facing served model name when given', () => {
    const servedModelNames = new Map([
      [
        'steramae/nvidia-llama-3-3-nemotron-super-49b-v1-5',
        'nvidia/llama-3.3-nemotron-super-49b-v1.5',
      ],
    ]);
    expect(
      buildModelConfigs(
        [model({ model: 'steramae/nvidia-llama-3-3-nemotron-super-49b-v1-5', provider: '' })],
        servedModelNames
      )
    ).toEqual([
      {
        alias: 'default',
        model: 'nvidia/llama-3.3-nemotron-super-49b-v1.5',
        inference_parameters: { generation_type: 'chat-completion', max_tokens: 1024 },
        provider: '',
      },
    ]);
  });

  it('maps inference parameters and trims the alias', () => {
    expect(
      buildModelConfigs([
        model({
          alias: '  spaced  ',
          inferenceParams: { temperature: 0.7, top_p: 0.9, max_tokens: 512 },
        }),
      ])
    ).toEqual([
      {
        alias: 'spaced',
        model: 'nvidia/llama-3.3-nemotron-super-49b-v1',
        provider: 'nvidia',
        inference_parameters: {
          generation_type: 'chat-completion',
          temperature: 0.7,
          top_p: 0.9,
          max_tokens: 512,
        },
      },
    ]);
  });

  it('emits embedding inference parameters and forwards extra_body for embedding models', () => {
    expect(
      buildModelConfigs([
        model({
          alias: 'embedder',
          model: 'nvidia/nv-embedqa-e5-v5',
          provider: 'steramae/build',
          inferenceParams: {
            generation_type: 'embedding',
            encoding_format: 'float',
            extra_body: { input_type: 'query', truncate: 'NONE' },
          },
        }),
      ])
    ).toEqual([
      {
        alias: 'embedder',
        model: 'nvidia/nv-embedqa-e5-v5',
        provider: 'steramae/build',
        inference_parameters: {
          generation_type: 'embedding',
          encoding_format: 'float',
          extra_body: { input_type: 'query', truncate: 'NONE' },
        },
      },
    ]);
  });
});
