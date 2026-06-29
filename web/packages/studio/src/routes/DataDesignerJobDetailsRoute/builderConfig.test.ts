// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  formatColumnTypeBreakdown,
  summarizeBuilderConfig,
} from '@studio/routes/DataDesignerJobDetailsRoute/builderConfig';

const fullConfig = {
  library_version: '1.2.3',
  data_designer: {
    columns: [
      { name: 'product_id', column_type: 'sampler' },
      { name: 'category', column_type: 'sampler' },
      { name: 'review_text', column_type: 'llm-text', model_alias: 'review-model' },
      { name: 'sentiment', column_type: 'llm-structured', model_alias: 'review-model' },
    ],
    model_configs: [
      { alias: 'review-model', model: 'meta/llama-3.1-8b-instruct', provider: 'nvidia' },
    ],
    seed_config: { source: { seed_type: 'fileset' }, sampling_strategy: 'shuffle' },
    constraints: [{}, {}],
    profilers: [{}],
    processors: [{ name: 'dedup' }, { name: 'drop-pii' }],
  },
};

describe('summarizeBuilderConfig', () => {
  it('returns null for non-config payloads', () => {
    expect(summarizeBuilderConfig(null)).toBeNull();
    expect(summarizeBuilderConfig('not json')).toBeNull();
    expect(summarizeBuilderConfig({})).toBeNull();
    expect(summarizeBuilderConfig([])).toBeNull();
  });

  it('extracts columns, models, seed, and counts from a full config', () => {
    const summary = summarizeBuilderConfig(fullConfig);
    expect(summary).not.toBeNull();
    expect(summary?.columnCount).toBe(4);
    expect(summary?.columns).toEqual([
      { name: 'product_id', type: 'sampler', modelAlias: undefined },
      { name: 'category', type: 'sampler', modelAlias: undefined },
      { name: 'review_text', type: 'llm-text', modelAlias: 'review-model' },
      { name: 'sentiment', type: 'llm-structured', modelAlias: 'review-model' },
    ]);
    expect(summary?.models).toEqual([
      { alias: 'review-model', model: 'meta/llama-3.1-8b-instruct', provider: 'nvidia' },
    ]);
    expect(summary?.seed).toEqual({ type: 'fileset', samplingStrategy: 'shuffle' });
    expect(summary?.constraintCount).toBe(2);
    expect(summary?.profilerCount).toBe(1);
    expect(summary?.processorNames).toEqual(['dedup', 'drop-pii']);
    expect(summary?.libraryVersion).toBe('1.2.3');
  });

  it('orders the column-type breakdown by count then name', () => {
    const summary = summarizeBuilderConfig(fullConfig);
    expect(summary?.columnTypeBreakdown).toEqual([
      { type: 'sampler', count: 2 },
      { type: 'llm-structured', count: 1 },
      { type: 'llm-text', count: 1 },
    ]);
    expect(formatColumnTypeBreakdown(summary!)).toBe('2 sampler, 1 llm-structured, 1 llm-text');
  });

  it('tolerates a minimal config and omits the absent seed', () => {
    const summary = summarizeBuilderConfig({ data_designer: { columns: [] } });
    expect(summary).not.toBeNull();
    expect(summary?.columnCount).toBe(0);
    expect(summary?.models).toEqual([]);
    expect(summary?.seed).toBeUndefined();
    expect(summary?.constraintCount).toBe(0);
    expect(summary?.processorNames).toEqual([]);
    expect(summary?.libraryVersion).toBeUndefined();
  });

  it('falls back gracefully for malformed entries', () => {
    const summary = summarizeBuilderConfig({
      data_designer: {
        columns: [{ column_type: 'sampler' }, { name: 'x' }, 'garbage'],
        model_configs: [{ alias: 'm1' }],
      },
    });
    expect(summary?.columns).toEqual([
      { name: '(unnamed)', type: 'sampler', modelAlias: undefined },
      { name: 'x', type: 'unknown', modelAlias: undefined },
      { name: '(unnamed)', type: 'unknown', modelAlias: undefined },
    ]);
    expect(summary?.models).toEqual([{ alias: 'm1', model: '—', provider: undefined }]);
  });
});
