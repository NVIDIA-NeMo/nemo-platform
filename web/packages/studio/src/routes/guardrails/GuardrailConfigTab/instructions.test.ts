// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Instruction } from '@nemo/sdk/generated/platform/schema';
import {
  getGeneralInstruction,
  setGeneralInstruction,
} from '@studio/routes/guardrails/GuardrailConfigTab/instructions';

describe('getGeneralInstruction', () => {
  it('returns the first general instruction content', () => {
    const instructions: Instruction[] = [
      { type: 'other', content: 'x' },
      { type: 'general', content: 'be helpful' },
    ];
    expect(getGeneralInstruction(instructions)).toBe('be helpful');
  });

  it('returns empty string when there is no general instruction', () => {
    expect(getGeneralInstruction([{ type: 'other', content: 'x' }])).toBe('');
    expect(getGeneralInstruction(undefined)).toBe('');
  });
});

describe('setGeneralInstruction', () => {
  it('appends a general instruction when none exists', () => {
    const result = setGeneralInstruction([{ type: 'other', content: 'x' }], 'be kind');
    expect(result).toEqual([
      { type: 'other', content: 'x' },
      { type: 'general', content: 'be kind' },
    ]);
  });

  it('creates the array when instructions are undefined', () => {
    expect(setGeneralInstruction(undefined, 'be kind')).toEqual([
      { type: 'general', content: 'be kind' },
    ]);
  });

  it('updates the first general instruction in place, preserving order', () => {
    const result = setGeneralInstruction(
      [
        { type: 'other', content: 'x' },
        { type: 'general', content: 'old' },
        { type: 'other', content: 'y' },
      ],
      'new'
    );
    expect(result).toEqual([
      { type: 'other', content: 'x' },
      { type: 'general', content: 'new' },
      { type: 'other', content: 'y' },
    ]);
  });

  it('only touches the first general instruction when there are several', () => {
    const result = setGeneralInstruction(
      [
        { type: 'general', content: 'first' },
        { type: 'general', content: 'second' },
      ],
      'updated'
    );
    expect(result).toEqual([
      { type: 'general', content: 'updated' },
      { type: 'general', content: 'second' },
    ]);
  });

  it('removes the first general instruction when content is blank', () => {
    const result = setGeneralInstruction(
      [
        { type: 'other', content: 'x' },
        { type: 'general', content: 'drop me' },
      ],
      '   '
    );
    expect(result).toEqual([{ type: 'other', content: 'x' }]);
  });

  it('is a no-op on blank content when there is no general instruction', () => {
    const instructions: Instruction[] = [{ type: 'other', content: 'x' }];
    expect(setGeneralInstruction(instructions, '')).toEqual(instructions);
  });
});
