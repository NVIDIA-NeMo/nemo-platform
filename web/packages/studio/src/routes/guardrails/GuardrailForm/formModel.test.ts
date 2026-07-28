// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigOutput } from '@nemo/sdk/generated/platform/schema';
import { applyFormToConfig } from '@studio/routes/guardrails/GuardrailForm/formModel';

describe('applyFormToConfig', () => {
  it('persists removal of the sole general instruction as an empty list', () => {
    const data: RailsConfigOutput = {
      instructions: [{ type: 'general', content: 'Be helpful.' }],
    };
    const result = applyFormToConfig(data, { generalInstruction: '', sampleConversation: '' });
    expect(result.instructions).toEqual([]);
  });

  it('keeps other instructions when the general one is cleared', () => {
    const data: RailsConfigOutput = {
      instructions: [
        { type: 'general', content: 'Be helpful.' },
        { type: 'sample_conversation', content: 'user: hi' },
      ],
    };
    const result = applyFormToConfig(data, { generalInstruction: '', sampleConversation: '' });
    expect(result.instructions).toEqual([{ type: 'sample_conversation', content: 'user: hi' }]);
  });

  it('updates the general instruction while preserving unexposed config fields', () => {
    const data = {
      instructions: [{ type: 'general', content: 'Old.' }],
      models: [{ type: 'main', engine: 'openai', model: 'gpt-4' }],
    } as RailsConfigOutput;
    const result = applyFormToConfig(data, { generalInstruction: 'New.', sampleConversation: '' });
    expect(result.instructions).toEqual([{ type: 'general', content: 'New.' }]);
    expect(result.models).toEqual(data.models);
  });

  it('omits an empty sample conversation', () => {
    const result = applyFormToConfig(undefined, {
      generalInstruction: 'Hi.',
      sampleConversation: '',
    });
    expect(result.sample_conversation).toBeUndefined();
  });
});
