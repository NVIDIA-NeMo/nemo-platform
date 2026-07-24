// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  DETECTION_ROLES,
  REPLACE_ROLE,
  REWRITE_ROLES,
  ROLE_LABELS,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import {
  AnonymizerFormData,
  buildAnonymizerJobRequest,
  getAnonymizerFormDefaults,
} from '@studio/routes/AnonymizerBuilderRoute/schema';

const ALL_ROLES = [...DETECTION_ROLES, REPLACE_ROLE, ...REWRITE_ROLES];

const roleModels = (model: string, provider: string) =>
  Object.fromEntries(ALL_ROLES.map((role) => [role, { modelId: role, model, provider }]));

const form = (overrides: Partial<AnonymizerFormData> = {}): AnonymizerFormData => ({
  ...getAnonymizerFormDefaults(),
  source: 'https://example.com/data.csv',
  roleModels: roleModels('openai/gpt-oss-120b', 'default/nvidia'),
  ...overrides,
});

describe('buildAnonymizerJobRequest', () => {
  it('routes the four replace strategies to config.replace with the kind tag', () => {
    for (const strategy of ['substitute', 'redact', 'annotate', 'hash'] as const) {
      const req = buildAnonymizerJobRequest(form({ strategy }));
      expect(req.spec.config).toEqual({ replace: { kind: strategy } });
    }
  });

  it('routes rewrite to config.rewrite', () => {
    const req = buildAnonymizerJobRequest(form({ strategy: 'rewrite' }));
    expect(req.spec.config).toEqual({ rewrite: {} });
  });

  it('trims the source and omits empty optional fields', () => {
    const req = buildAnonymizerJobRequest(
      form({ source: '  s3://x.csv  ', textColumn: '', dataSummary: '   ' })
    );
    expect(req.spec.data.source).toBe('s3://x.csv');
    expect(req.spec.data.text_column).toBeUndefined();
    expect(req.spec.data.data_summary).toBeUndefined();
  });

  it('deduplicates identical role models into a single model_config', () => {
    const req = buildAnonymizerJobRequest(form({ strategy: 'substitute' }));
    expect(req.spec.model_configs).toEqual([
      { alias: 'model-1', model: 'openai/gpt-oss-120b', provider: 'default/nvidia' },
    ]);
  });

  it('emits one model_config per unique model+provider', () => {
    const models = roleModels('openai/gpt-oss-120b', 'default/nvidia');
    models[DETECTION_ROLES[0]] = {
      modelId: 'gliner',
      model: 'nvidia/gliner-pii',
      provider: 'default/nvidia',
    };
    const req = buildAnonymizerJobRequest(form({ strategy: 'substitute', roleModels: models }));
    expect(req.spec.model_configs).toHaveLength(2);
    expect(req.spec.selected_models?.detection?.[DETECTION_ROLES[0]]).not.toBe(
      req.spec.selected_models?.replace?.[REPLACE_ROLE]
    );
  });

  it('maps detection + replace roles for substitute, detection + rewrite for rewrite', () => {
    const sub = buildAnonymizerJobRequest(form({ strategy: 'substitute' })).spec.selected_models;
    expect(sub?.detection?.entity_detector).toBe('model-1');
    expect(sub?.replace?.replacement_generator).toBe('model-1');
    expect(sub?.rewrite).toBeUndefined();

    const rew = buildAnonymizerJobRequest(form({ strategy: 'rewrite' })).spec.selected_models;
    expect(rew?.detection?.entity_detector).toBe('model-1');
    expect(rew?.rewrite?.rewriter).toBe('model-1');
    expect(rew?.replace).toBeUndefined();
  });

  it('maps only detection roles for redact/annotate/hash', () => {
    for (const strategy of ['redact', 'annotate', 'hash'] as const) {
      const selected = buildAnonymizerJobRequest(form({ strategy })).spec.selected_models;
      expect(selected?.detection?.entity_detector).toBe('model-1');
      expect(selected?.replace).toBeUndefined();
      expect(selected?.rewrite).toBeUndefined();
    }
  });

  it('exposes a label for every configurable role', () => {
    for (const role of ALL_ROLES) {
      expect(ROLE_LABELS[role]).toBeTruthy();
    }
  });

  it('attaches inference_parameters and splits configs when params differ', () => {
    const models = roleModels('openai/gpt-oss-120b', 'default/nvidia');
    models[DETECTION_ROLES[0]] = {
      modelId: 'gpt',
      model: 'openai/gpt-oss-120b',
      provider: 'default/nvidia',
      params: { temperature: 0.1 },
    };
    const req = buildAnonymizerJobRequest(form({ strategy: 'substitute', roleModels: models }));
    // Same model+provider but one role has params → two distinct configs.
    expect(req.spec.model_configs).toHaveLength(2);
    const withParams = req.spec.model_configs?.find((c) => c.inference_parameters);
    expect(withParams?.inference_parameters).toEqual({ temperature: 0.1 });
  });
});
