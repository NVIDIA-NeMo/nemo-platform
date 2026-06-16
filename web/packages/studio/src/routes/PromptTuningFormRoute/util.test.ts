// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { validateModelName } from '@studio/routes/PromptTuningFormRoute/utils';

describe('validateModelName', () => {
  it('allows valid model names', () => {
    const validNames = [
      'model',
      'model_name',
      'model-NaMe',
      'modeLL0123',
      '_model-', // this is weird looking but I don't know that we should stop users from using it?
      '_model___name01',
      'model-1.2',
      'model@custom-3',
    ];
    validNames.forEach((name) => {
      expect(validateModelName(name)).toEqual(true);
    });
  });
  it('disallows invalid model names', () => {
    const invalidNames = ['model/slash', 'model space', '    model', 'model!!', 'modél'];
    invalidNames.forEach((name) => {
      expect(validateModelName(name)).toEqual(false);
    });
  });
});
