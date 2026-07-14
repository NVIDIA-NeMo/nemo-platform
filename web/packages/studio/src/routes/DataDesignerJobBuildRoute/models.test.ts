// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import type { ModelProvider } from '@nemo/sdk/generated/platform/schema';
import {
  type BuilderModel,
  buildModelConfigs,
  buildModelsFromTemplate,
  buildServedModelNames,
  builderModelFromSelection,
  defaultModelAlias,
  firstAvailableModel,
  modelIdForModel,
  providerForModel,
  resolveTemplateModel,
  validateModelAlias,
  validateModels,
} from '@studio/routes/DataDesignerJobBuildRoute/models';

const model = (overrides: Partial<BuilderModel> = {}): BuilderModel => ({
  id: 'model-0',
  alias: 'default',
  model: 'openai/gpt-4o-mini',
  provider: 'openai',
  inferenceParams: {},
  ...overrides,
});

describe('defaultModelAlias', () => {
  it('returns the first unused model_N alias', () => {
    expect(defaultModelAlias(new Set())).toBe('model_1');
    expect(defaultModelAlias(new Set(['model_1', 'model_2']))).toBe('model_3');
  });
});

describe('providerForModel', () => {
  const groups = [
    {
      workspace: 'steramae',
      models: [
        { workspace: 'steramae', name: 'gpt-oss', model_providers: ['steramae/build'] },
        {
          workspace: 'steramae',
          name: 'nvidia-llama-3-3-nemotron-super-49b-v1-5',
          model_providers: ['steramae/build'],
        },
        { workspace: 'steramae', name: 'no-provider' },
      ],
    },
  ] as unknown as ModelWorkspaceGroup[];

  it('returns the model’s first provider ref', () => {
    expect(providerForModel(groups, 'steramae/gpt-oss')).toBe('steramae/build');
  });

  it('returns empty string when the model or its provider is missing', () => {
    expect(providerForModel(groups, 'steramae/no-provider')).toBe('');
    expect(providerForModel(groups, 'steramae/unknown')).toBe('');
  });

  it('firstAvailableModel picks the first model and its provider', () => {
    expect(firstAvailableModel(groups)).toEqual({
      model: 'steramae/gpt-oss',
      provider: 'steramae/build',
    });
    expect(firstAvailableModel([])).toBeNull();
  });

  it('resolveTemplateModel prefers a model matching the name across workspaces', () => {
    expect(resolveTemplateModel(groups, 'nvidia-llama-3-3-nemotron-super-49b-v1-5')).toEqual({
      model: 'steramae/nvidia-llama-3-3-nemotron-super-49b-v1-5',
      provider: 'steramae/build',
    });
  });

  it('resolveTemplateModel matches a full URN too', () => {
    expect(resolveTemplateModel(groups, 'steramae/gpt-oss')).toEqual({
      model: 'steramae/gpt-oss',
      provider: 'steramae/build',
    });
  });

  it('resolveTemplateModel falls back to the first model when the preferred is absent', () => {
    expect(resolveTemplateModel(groups, 'not-in-workspace')).toEqual({
      model: 'steramae/gpt-oss',
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
        { model_entity_id: 'steramae/gpt-oss', served_model_name: 'openai/gpt-oss-120b' },
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
    expect(names.get('steramae/gpt-oss')).toBe('openai/gpt-oss-120b');
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
      { id: 'model-2', alias: 'default', model: '', provider: '', inferenceParams: {} },
    ]);
  });

  it('carries a preferred model and inference params through', () => {
    const models = buildModelsFromTemplate([
      { alias: 'judge', model: 'nvidia/gpt-oss', inferenceParams: { temperature: 0 } },
    ]);
    expect(models[0]).toMatchObject({
      alias: 'judge',
      model: 'nvidia/gpt-oss',
      inferenceParams: { temperature: 0 },
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
        { model: 'openai/gpt-4o-mini' },
        'default/nvidia-build',
        new Set(['model_1'])
      )
    ).toEqual({
      id: 'model-5',
      alias: 'model_2',
      model: 'openai/gpt-4o-mini',
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

describe('buildModelConfigs', () => {
  it('returns undefined when there are no models', () => {
    expect(buildModelConfigs([])).toBeUndefined();
  });

  it('omits empty optional fields but always includes inference parameters with defaults', () => {
    expect(buildModelConfigs([model({ provider: '' })])).toEqual([
      {
        alias: 'default',
        model: 'openai/gpt-4o-mini',
        provider: '',
        inference_parameters: {
          generation_type: 'chat-completion',
          max_tokens: 1024,
        },
      },
    ]);
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
        model: 'openai/gpt-4o-mini',
        provider: 'openai',
        inference_parameters: {
          generation_type: 'chat-completion',
          temperature: 0.7,
          top_p: 0.9,
          max_tokens: 512,
        },
      },
    ]);
  });
});
