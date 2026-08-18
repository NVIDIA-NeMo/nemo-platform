// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import {
  applyFormToConfig,
  mapConfigToForm,
} from '@studio/routes/guardrails/GuardrailForm/formModel';

describe('mapConfigToForm', () => {
  it('deep-clones so edits never mutate the cached server config', () => {
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
  it('returns the working copy as the payload', () => {
    const values = mapConfigToForm({
      passthrough: true,
      rails: { output: { flows: ['self check output'] } },
    } as RailsConfig);

    expect(applyFormToConfig(values)).toEqual({
      passthrough: true,
      rails: { output: { flows: ['self check output'] } },
    });
  });

  it('round-trips fields no part of the editor models', () => {
    // The backend ignores unknown top-level keys, but a config authored from files or the
    // CLI can carry Colang-era fields that must survive an unrelated edit here.
    const data = {
      user_messages: { greeting: ['hello'] },
      import_paths: ['./shared'],
    } as unknown as RailsConfig;

    expect(applyFormToConfig(mapConfigToForm(data))).toEqual(data);
  });
});
