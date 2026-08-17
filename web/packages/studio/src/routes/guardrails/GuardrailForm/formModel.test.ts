// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import {
  applyFormToConfig,
  type GuardrailFormValues,
  mapConfigToForm,
} from '@studio/routes/guardrails/GuardrailForm/formModel';

/** The form as the UI would hold it, with one field overridden as if the user typed. */
const editedForm = (
  data: RailsConfig | undefined,
  overrides: Partial<GuardrailFormValues>
): GuardrailFormValues => ({ ...mapConfigToForm(data), ...overrides });

describe('mapConfigToForm', () => {
  it('deep-clones the working copy so rail edits never mutate the cached server config', () => {
    const data = {
      rails: { input: { flows: ['self check input'] } },
    } as RailsConfig;

    const values = mapConfigToForm(data);
    values.config.rails?.input?.flows?.push('jailbreak detection model');

    expect(data.rails?.input?.flows).toEqual(['self check input']);
  });

  it('represents a config with no data as an empty document', () => {
    expect(mapConfigToForm(undefined).config).toEqual({});
  });
});

describe('applyFormToConfig', () => {
  it('persists removal of the sole general instruction as an empty list', () => {
    const data: RailsConfig = {
      instructions: [{ type: 'general', content: 'Be helpful.' }],
    };
    const result = applyFormToConfig(data, editedForm(data, { generalInstruction: '' }));
    expect(result.instructions).toEqual([]);
  });

  it('keeps other instructions when the general one is cleared', () => {
    const data: RailsConfig = {
      instructions: [
        { type: 'general', content: 'Be helpful.' },
        { type: 'sample_conversation', content: 'user: hi' },
      ],
    };
    const result = applyFormToConfig(data, editedForm(data, { generalInstruction: '' }));
    expect(result.instructions).toEqual([{ type: 'sample_conversation', content: 'user: hi' }]);
  });

  it('updates the general instruction while preserving unexposed config fields', () => {
    const data = {
      instructions: [{ type: 'general', content: 'Old.' }],
      models: [{ type: 'main', engine: 'openai', model: 'gpt-4' }],
    } as RailsConfig;
    const result = applyFormToConfig(data, editedForm(data, { generalInstruction: 'New.' }));
    expect(result.instructions).toEqual([{ type: 'general', content: 'New.' }]);
    expect(result.models).toEqual(data.models);
  });

  it('omits an empty sample conversation', () => {
    const result = applyFormToConfig(
      undefined,
      editedForm(undefined, { generalInstruction: 'Hi.' })
    );
    expect(result.sample_conversation).toBeUndefined();
  });

  it('carries rail edits made against the working copy', () => {
    const data = { passthrough: true } as RailsConfig;
    const values = editedForm(data, {
      config: {
        passthrough: true,
        rails: { input: { flows: ['self check input'] } },
        prompts: [{ task: 'self_check_input', content: 'Block?' }],
      },
    });

    const result = applyFormToConfig(data, values);

    expect(result.rails?.input?.flows).toEqual(['self check input']);
    expect(result.prompts).toEqual([{ task: 'self_check_input', content: 'Block?' }]);
    expect(result.passthrough).toBe(true);
  });

  it('round-trips fields no part of the editor models', () => {
    // The backend ignores unknown top-level keys, but a config authored from files or the
    // CLI can carry Colang-era fields that must survive an unrelated edit here.
    const data = {
      user_messages: { greeting: ['hello'] },
      import_paths: ['./shared'],
    } as unknown as RailsConfig;

    const result = applyFormToConfig(data, editedForm(data, { generalInstruction: 'Hi.' }));

    expect(result).toMatchObject({
      user_messages: { greeting: ['hello'] },
      import_paths: ['./shared'],
    });
  });
});
