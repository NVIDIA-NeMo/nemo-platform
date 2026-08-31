// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Model } from '@nemo/sdk/generated/platform/schema';
import {
  getMainModel,
  getMainModelName,
  setMainModelName,
} from '@studio/routes/guardrails/GuardrailConfigTab/mainModel';

const TASK_LLM: Model = {
  type: 'content_safety',
  engine: 'nim',
  model: 'system/nemoguard-8b-content-safety',
};

describe('getMainModel', () => {
  it('returns undefined when there are no models', () => {
    expect(getMainModel(undefined)).toBeUndefined();
  });

  it('ignores task LLMs', () => {
    expect(getMainModel([TASK_LLM])).toBeUndefined();
    expect(getMainModelName([TASK_LLM])).toBe('');
  });

  it('finds the main entry', () => {
    const main: Model = { type: 'main', engine: 'nim', model: 'default/llama' };
    expect(getMainModelName([TASK_LLM, main])).toBe('default/llama');
  });
});

describe('setMainModelName', () => {
  it('appends a main entry with the default engine and chat mode', () => {
    expect(setMainModelName(undefined, 'default/llama')).toEqual([
      { type: 'main', engine: 'nim', mode: 'chat', model: 'default/llama' },
    ]);
  });

  it('preserves task LLMs and their order', () => {
    const result = setMainModelName([TASK_LLM], 'default/llama');
    expect(result?.[0]).toEqual(TASK_LLM);
    expect(result).toHaveLength(2);
  });

  it('changes only the name on an existing main entry', () => {
    const main: Model = {
      type: 'main',
      engine: 'openai',
      mode: 'chat',
      model: 'old',
      parameters: { temperature: 0.2 },
    };
    expect(setMainModelName([main], 'new')).toEqual([{ ...main, model: 'new' }]);
  });

  it('drops the main entry when cleared, keeping task LLMs', () => {
    const main: Model = { type: 'main', engine: 'nim', model: 'default/llama' };
    expect(setMainModelName([TASK_LLM, main], '')).toEqual([TASK_LLM]);
  });

  it('collapses to undefined when clearing the only entry', () => {
    const main: Model = { type: 'main', engine: 'nim', model: 'default/llama' };
    expect(setMainModelName([main], '')).toBeUndefined();
  });

  it('is a no-op when clearing with no main entry present', () => {
    const models = [TASK_LLM];
    expect(setMainModelName(models, '')).toBe(models);
  });
});
