// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getDefaultMappingValue,
  getDefaultOutputFilepath,
  getKeyDescriptions,
  getKeySuggestions,
  getPrefilledSchema,
  getRequiredKeys,
  TARGET_FORMAT_DEFINITIONS,
  TARGET_FORMATS,
} from '@studio/components/FilesTable/TransformFileModal/targetFormats';

describe('target format registry', () => {
  it('documents every field of every format', () => {
    for (const format of TARGET_FORMATS) {
      const descriptions = getKeyDescriptions(format);
      for (const field of TARGET_FORMAT_DEFINITIONS[format].fields) {
        expect(descriptions[field.key]).toBeTruthy();
      }
    }
  });

  it('prefills a row for every required field', () => {
    for (const format of TARGET_FORMATS) {
      const prefilled = getPrefilledSchema(format) ?? {};
      for (const key of getRequiredKeys(format)) {
        expect(prefilled).toHaveProperty(key);
      }
    }
  });

  it('suggests an output file beside the source, never on top of it', () => {
    for (const format of TARGET_FORMATS) {
      const source = 'nested/dir/data.csv';
      const output = getDefaultOutputFilepath(format, source);
      expect(output).not.toBe(source);
      expect(output.startsWith('nested/dir/data-')).toBe(true);
      expect(output.endsWith('.jsonl')).toBe(true);
    }
  });

  it('handles a bare filename and a missing source', () => {
    expect(getDefaultOutputFilepath('custom', 'data.jsonl')).toBe('data-transformed.jsonl');
    expect(getDefaultOutputFilepath('custom', 'noextension')).toBe('noextension-transformed.jsonl');
    expect(getDefaultOutputFilepath('custom', '')).toBe('');
  });

  it('leaves the custom format free-form', () => {
    expect(getPrefilledSchema('custom')).toBeUndefined();
    expect(getKeySuggestions('custom')).toBeUndefined();
    expect(getDefaultMappingValue('custom', 'anything', [])).toBe('{{{anything}}}');
  });
});

describe('agent eval task format', () => {
  it('resolves help text from the generated zod describe blocks', () => {
    const descriptions = getKeyDescriptions('agent-eval-task');
    expect(descriptions.intent).toContain(
      'Human-readable description of the desired agent behavior.'
    );
    expect(descriptions['inputs.instruction']).toContain("The agent's instruction (its prompt).");
    expect(descriptions.metrics).toContain('Metrics that score this task');
    expect(descriptions.metadata).toContain('Key/value annotations');
  });

  it('falls back to the row number when the file has no id column', () => {
    expect(getDefaultMappingValue('agent-eval-task', 'id', ['question'])).toBe('task-{{@row}}');
  });

  it('maps id to the source column when one is present', () => {
    expect(getDefaultMappingValue('agent-eval-task', 'id', ['task_id'])).toBe('{{{task_id}}}');
  });

  it('auto-maps the instruction from a likely prompt column', () => {
    expect(getDefaultMappingValue('agent-eval-task', 'inputs.instruction', ['prompt'])).toBe(
      '{{{prompt}}}'
    );
    expect(getDefaultMappingValue('agent-eval-task', 'inputs.instruction', ['other'])).toBe('');
  });
});
