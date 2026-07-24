// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  AnonymizerFormData,
  buildAnonymizerJobRequest,
  getAnonymizerFormDefaults,
} from '@studio/routes/AnonymizerBuilderRoute/schema';

const form = (overrides: Partial<AnonymizerFormData> = {}): AnonymizerFormData => ({
  ...getAnonymizerFormDefaults(),
  source: 'https://example.com/data.csv',
  modelId: 'default/gpt',
  model: 'openai/gpt-oss-120b',
  provider: 'default/nvidia',
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

  it('passes through populated columns and a trimmed name', () => {
    const req = buildAnonymizerJobRequest(
      form({ name: '  job-1 ', textColumn: 'biography', dataSummary: 'profiles' })
    );
    expect(req.name).toBe('job-1');
    expect(req.spec.data.text_column).toBe('biography');
    expect(req.spec.data.data_summary).toBe('profiles');
  });

  it('emits a single model_config from the selected model and provider', () => {
    const req = buildAnonymizerJobRequest(form());
    expect(req.spec.model_configs).toEqual([
      { alias: 'anonymizer-model', model: 'openai/gpt-oss-120b', provider: 'default/nvidia' },
    ]);
  });

  it('maps detection + replace roles for substitute, detection + rewrite for rewrite', () => {
    const sub = buildAnonymizerJobRequest(form({ strategy: 'substitute' })).spec.selected_models;
    expect(sub?.detection?.entity_detector).toBe('anonymizer-model');
    expect(sub?.replace?.replacement_generator).toBe('anonymizer-model');
    expect(sub?.rewrite).toBeUndefined();

    const rew = buildAnonymizerJobRequest(form({ strategy: 'rewrite' })).spec.selected_models;
    expect(rew?.detection?.entity_detector).toBe('anonymizer-model');
    expect(rew?.rewrite?.rewriter).toBe('anonymizer-model');
    expect(rew?.replace).toBeUndefined();
  });

  it('maps only detection roles for redact/annotate/hash', () => {
    for (const strategy of ['redact', 'annotate', 'hash'] as const) {
      const selected = buildAnonymizerJobRequest(form({ strategy })).spec.selected_models;
      expect(selected?.detection?.entity_detector).toBe('anonymizer-model');
      expect(selected?.replace).toBeUndefined();
      expect(selected?.rewrite).toBeUndefined();
    }
  });
});
