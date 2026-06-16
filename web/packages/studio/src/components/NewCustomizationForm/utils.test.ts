// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { refineModelName } from '@studio/components/NewCustomizationForm/utils';

const trainingParams = {
  type: 'sft' as const,
  peft: {
    type: 'lora' as const,
    rank: 16,
    alpha: 16,
    dropout: 0.1,
    merge: false,
    use_dora: false,
  },
};

describe('refineModelName', () => {
  it('should return true if the generated model name is valid', () => {
    expect(
      refineModelName({
        model: 'default/meta-llama-3.2-1b',
        training: trainingParams,
      })
    ).toBe(true);
  });

  it('should return true if a short output name is provided', () => {
    expect(refineModelName({ output: { name: 'test-model-name' } })).toBe(true);
  });

  it('should return false if generated model name is too long', () => {
    expect(
      refineModelName({
        model: 'default/meta-llama-3.2-1b-qa-generation-fileset-TEbtX4B5nuySgZW4YEHa5i',
        training: trainingParams,
      })
    ).toBe(false);
  });

  it('should return false if the output model name is too long', () => {
    expect(
      refineModelName({
        output: { name: 'nvidia-test-model-name-that-is-too-long-to-be-generated-and-validated' },
      })
    ).toBe(false);
  });
});
