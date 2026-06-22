// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  buildSuggestedModelOptions,
  pickDefaultModelName,
} from '@studio/util/buildSuggestedModelOptions';

describe('buildSuggestedModelOptions', () => {
  it('splits NVIDIA Nemotron models into the suggested group and the rest into all', () => {
    const options = buildSuggestedModelOptions([
      { name: 'nvidia/nemotron-super' },
      { name: 'openai/gpt-4o' },
    ]);
    expect(options).toEqual([
      { value: 'nvidia/nemotron-super', label: 'nvidia/nemotron-super', group: 'suggested' },
      { value: 'openai/gpt-4o', label: 'openai/gpt-4o', group: 'all' },
    ]);
  });

  it('excludes non-chat-LLM candidates (embedding/rerank/safety/vl/...)', () => {
    const options = buildSuggestedModelOptions([
      { name: 'nvidia/embed-qa' },
      { name: 'nvidia/llama-guard' },
      { name: 'some/reranker' },
      { name: 'openai/gpt-4o' },
    ]);
    expect(options.map((o) => o.value)).toEqual(['openai/gpt-4o']);
  });

  it('dedupes duplicate model names so option values stay unique', () => {
    const options = buildSuggestedModelOptions([
      { name: 'nvidia/nemotron-super' },
      { name: 'nvidia/nemotron-super' },
      { name: 'openai/gpt-4o' },
      { name: 'openai/gpt-4o' },
    ]);
    expect(options).toEqual([
      { value: 'nvidia/nemotron-super', label: 'nvidia/nemotron-super', group: 'suggested' },
      { value: 'openai/gpt-4o', label: 'openai/gpt-4o', group: 'all' },
    ]);
  });

  it('does not repeat a suggested model under all', () => {
    const options = buildSuggestedModelOptions([{ name: 'nvidia/nemotron-super' }]);
    expect(options).toEqual([
      { value: 'nvidia/nemotron-super', label: 'nvidia/nemotron-super', group: 'suggested' },
    ]);
  });
});

describe('pickDefaultModelName', () => {
  it('prefers a suggested model when one exists', () => {
    expect(
      pickDefaultModelName([{ name: 'openai/gpt-4o' }, { name: 'nvidia/nemotron-super' }])
    ).toBe('nvidia/nemotron-super');
  });

  it('falls back to the first chat-LLM candidate when none are suggested', () => {
    expect(pickDefaultModelName([{ name: 'nvidia/embed-qa' }, { name: 'openai/gpt-4o' }])).toBe(
      'openai/gpt-4o'
    );
  });

  it('returns undefined when there are no usable models', () => {
    expect(pickDefaultModelName([{ name: 'nvidia/embed-qa' }])).toBeUndefined();
  });
});
