// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import {
  countRails,
  getMainModelName,
  getRailCounts,
} from '@studio/components/dataViews/GuardrailsDataView/utils';

describe('countRails', () => {
  it('returns 0 for undefined data', () => {
    expect(countRails(undefined)).toBe(0);
  });

  it('returns 0 when data has no rails field', () => {
    expect(countRails({})).toBe(0);
  });

  it('returns 0 when rails object is present but empty', () => {
    const data: RailsConfig = { rails: {} };
    expect(countRails(data)).toBe(0);
  });

  it('counts input flows', () => {
    const data: RailsConfig = {
      rails: { input: { flows: ['check pii', 'check toxicity'] } },
    };
    expect(countRails(data)).toBe(2);
  });

  it('sums flows across input, output, and retrieval', () => {
    const data: RailsConfig = {
      rails: {
        input: { flows: ['a', 'b'] },
        output: { flows: ['c'] },
        retrieval: { flows: ['d', 'e', 'f'] },
      },
    };
    expect(countRails(data)).toBe(6);
  });

  it('handles partial rails (some sections undefined) without throwing', () => {
    const data: RailsConfig = {
      rails: {
        input: { flows: ['a'] },
        output: undefined,
        retrieval: {},
      },
    };
    expect(countRails(data)).toBe(1);
  });
});

describe('getMainModelName', () => {
  it('returns undefined for undefined data', () => {
    expect(getMainModelName(undefined)).toBeUndefined();
  });

  it('returns undefined when models array is absent', () => {
    expect(getMainModelName({})).toBeUndefined();
  });

  it('returns undefined when no model has type "main"', () => {
    const data: RailsConfig = {
      models: [{ type: 'embeddings', engine: 'openai', model: 'text-embedding-ada-002' }],
    };
    expect(getMainModelName(data)).toBeUndefined();
  });

  it('returns the model name of the main model', () => {
    const data: RailsConfig = {
      models: [
        { type: 'embeddings', engine: 'openai', model: 'text-embedding-ada-002' },
        { type: 'main', engine: 'openai', model: 'gpt-4' },
      ],
    };
    expect(getMainModelName(data)).toBe('gpt-4');
  });

  it('returns undefined when main model entry has no model field', () => {
    const data: RailsConfig = {
      models: [{ type: 'main', engine: 'openai' }],
    };
    expect(getMainModelName(data)).toBeUndefined();
  });
});

describe('getRailCounts', () => {
  it('returns zeros for undefined data', () => {
    expect(getRailCounts(undefined)).toEqual({ input: 0, output: 0 });
  });

  it('returns zeros when data has no rails', () => {
    expect(getRailCounts({})).toEqual({ input: 0, output: 0 });
  });

  it('counts input and output flows independently', () => {
    const data: RailsConfig = {
      rails: {
        input: { flows: ['check pii', 'check toxicity'] },
        output: { flows: ['mask pii output'] },
      },
    };
    expect(getRailCounts(data)).toEqual({ input: 2, output: 1 });
  });

  it('returns zero for a side that has no flows', () => {
    const data: RailsConfig = {
      rails: { input: { flows: ['a'] } },
    };
    expect(getRailCounts(data)).toEqual({ input: 1, output: 0 });
  });
});
