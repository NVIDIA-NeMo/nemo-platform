// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  isMappingDraftDirty,
  slugify,
  type MappingBaseline,
  type MappingDraft,
} from '@studio/components/transform/draft';
import { findOutputFormat, type OutputFormat } from '@studio/components/transform/formats';
import { autoMapFields } from '@studio/components/transform/template';

const agentEvalTask = findOutputFormat('agent-eval-task') as OutputFormat;
const columns = ['task_id', 'category', 'user_request', 'ideal_response'];

const baseline: MappingBaseline = {
  mappings: autoMapFields(agentEvalTask, columns, 'row_id'),
  customRows: [{ key: '', value: '' }],
};

const pristine: MappingDraft = {
  mappings: baseline.mappings,
  rawPaths: new Set(),
  customRows: baseline.customRows,
};

describe('slugify', () => {
  it('lowercases and hyphenates, trimming stray separators', () => {
    expect(slugify('  Support Evals (v2) ')).toBe('support-evals-v2');
  });
});

describe('isMappingDraftDirty', () => {
  it('is false for an untouched draft', () => {
    expect(isMappingDraftDirty(pristine, baseline)).toBe(false);
  });

  it('treats a blank mapping as equivalent to an absent one', () => {
    const draft = { ...pristine, mappings: { ...baseline.mappings, 'reference.other': '   ' } };
    expect(isMappingDraftDirty(draft, baseline)).toBe(false);
  });

  it('is true once a mapping is changed', () => {
    const draft = { ...pristine, mappings: { ...baseline.mappings, intent: '{{ other }}' } };
    expect(isMappingDraftDirty(draft, baseline)).toBe(true);
  });

  it('is true once an auto-mapped field is cleared', () => {
    const draft = { ...pristine, mappings: { ...baseline.mappings, id: '' } };
    expect(isMappingDraftDirty(draft, baseline)).toBe(true);
  });

  it('is true once a field is switched to a raw template', () => {
    expect(isMappingDraftDirty({ ...pristine, rawPaths: new Set(['id']) }, baseline)).toBe(true);
  });

  it('ignores empty custom rows but not filled ones', () => {
    expect(
      isMappingDraftDirty({ ...pristine, customRows: [{ key: '', value: '' }] }, baseline)
    ).toBe(false);
    expect(
      isMappingDraftDirty({ ...pristine, customRows: [{ key: 'id', value: '' }] }, baseline)
    ).toBe(true);
  });

  it('ignores custom rows that still match a seeded passthrough baseline', () => {
    const seeded: MappingBaseline = {
      ...baseline,
      customRows: [
        { key: 'task_id', value: '{{ task_id }}' },
        { key: '', value: '' },
      ],
    };

    expect(isMappingDraftDirty({ ...pristine, customRows: seeded.customRows }, seeded)).toBe(false);
    expect(
      isMappingDraftDirty(
        { ...pristine, customRows: [{ key: 'renamed', value: '{{ task_id }}' }] },
        seeded
      )
    ).toBe(true);
  });
});
