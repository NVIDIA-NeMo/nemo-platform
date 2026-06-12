// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigOutput } from '@nemo/sdk/generated/platform/schema';
import { countRails } from '@studio/components/dataViews/GuardrailsDataView/guardrailUtils';

describe('countRails', () => {
  it('returns 0 for undefined data', () => {
    expect(countRails(undefined)).toBe(0);
  });

  it('returns 0 when data has no rails field', () => {
    expect(countRails({})).toBe(0);
  });

  it('returns 0 when rails object is present but empty', () => {
    const data: RailsConfigOutput = { rails: {} };
    expect(countRails(data)).toBe(0);
  });

  it('counts input flows', () => {
    const data: RailsConfigOutput = {
      rails: { input: { flows: ['check pii', 'check toxicity'] } },
    };
    expect(countRails(data)).toBe(2);
  });

  it('sums flows across input, output, and retrieval', () => {
    const data: RailsConfigOutput = {
      rails: {
        input: { flows: ['a', 'b'] },
        output: { flows: ['c'] },
        retrieval: { flows: ['d', 'e', 'f'] },
      },
    };
    expect(countRails(data)).toBe(6);
  });

  it('handles partial rails (some sections undefined) without throwing', () => {
    const data: RailsConfigOutput = {
      rails: {
        input: { flows: ['a'] },
        output: undefined,
        retrieval: {},
      },
    };
    expect(countRails(data)).toBe(1);
  });
});
