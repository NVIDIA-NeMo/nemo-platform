// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  FILESET_NAME_MAX_LENGTH,
  FILESET_NAME_REGEXP,
  toValidFilesetName,
} from '@nemo/common/src/utils/filesetName';

describe('toValidFilesetName', () => {
  describe('produces output that satisfies FILESET_NAME_REGEXP', () => {
    const inputs = [
      'Qwen3.6-35B-A3B-MTP-GGUF', // HF slug with uppercase
      'mistralai/Mistral-7B-Instruct-v0.3',
      'hello world',
      '   leading-trailing   ',
      '123-starts-with-digit',
      '@starts-with-at',
      'has--double--dashes',
      'ends-with-dash-',
      'name.with.dots',
      'with_underscore',
      'has+plus@symbol',
      'a'.repeat(120), // long input
    ];
    it.each(inputs)('%s -> matches regex', (input) => {
      const out = toValidFilesetName(input);
      expect(out).toMatch(FILESET_NAME_REGEXP);
    });
  });

  it('lowercases letters', () => {
    expect(toValidFilesetName('ABC')).toBe('abc');
  });

  it('preserves a valid name unchanged (apart from trimming/lowercasing)', () => {
    expect(toValidFilesetName('qwen3.6-35b-a3b-mtp-gguf')).toBe('qwen3.6-35b-a3b-mtp-gguf');
  });

  it('replaces invalid chars with a single hyphen', () => {
    expect(toValidFilesetName('a b c')).toBe('a-b-c');
    expect(toValidFilesetName('a!!!b')).toBe('a-b');
  });

  it('collapses consecutive hyphens to one', () => {
    expect(toValidFilesetName('a--b---c')).toBe('a-b-c');
  });

  it('strips leading non-letter characters', () => {
    expect(toValidFilesetName('123abc')).toBe('abc');
    expect(toValidFilesetName('@home')).toBe('home');
    expect(toValidFilesetName('--leading-dash')).toBe('leading-dash');
  });

  it('strips trailing hyphens', () => {
    expect(toValidFilesetName('abc---')).toBe('abc');
  });

  it('truncates to FILESET_NAME_MAX_LENGTH and removes a newly-exposed trailing dash', () => {
    const padded = `a${'-b'.repeat(50)}`; // alternating ending up with - at boundary
    const out = toValidFilesetName(padded);
    expect(out.length).toBeLessThanOrEqual(FILESET_NAME_MAX_LENGTH);
    expect(out.endsWith('-')).toBe(false);
  });

  it('falls back to "fileset" when the sanitized result is too short', () => {
    expect(toValidFilesetName('')).toBe('fileset');
    expect(toValidFilesetName('---')).toBe('fileset');
    expect(toValidFilesetName('@')).toBe('fileset');
    expect(toValidFilesetName('a')).toBe('fileset'); // length 1 < min 2
  });

  it('handles HuggingFace-style slugs', () => {
    expect(toValidFilesetName('Llama-3.2-3B-Instruct')).toBe('llama-3.2-3b-instruct');
    expect(toValidFilesetName('SDXL/refiner-1.0')).toBe('sdxl-refiner-1.0');
  });

  it('handles NGC-style targets', () => {
    expect(toValidFilesetName('ngc_cli')).toBe('ngc_cli');
    expect(toValidFilesetName('llama2_7b_chat_hf')).toBe('llama2_7b_chat_hf');
  });
});
