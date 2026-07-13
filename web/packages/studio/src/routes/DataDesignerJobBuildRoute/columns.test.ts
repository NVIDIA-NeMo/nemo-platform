// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { COLUMN_TYPE_GROUPS } from '@studio/components/AddColumnPalette/constants';
import type { ColumnTypeOption } from '@studio/components/AddColumnPalette/types';
import {
  type BuilderColumn,
  buildColumnsFromTemplate,
  buildGraph,
  defaultColumnName,
  extractJinjaReferences,
  findColumnOption,
  validateColumnName,
} from '@studio/routes/DataDesignerJobBuildRoute/columns';

const optionFor = (columnType: string, samplerType?: string): ColumnTypeOption => {
  const found = findColumnOption({ columnType, samplerType } as never);
  if (!found) throw new Error(`no palette option for ${columnType}/${samplerType}`);
  return found;
};

const column = (
  id: string,
  name: string,
  columnType: string,
  values: Record<string, string>
): BuilderColumn => ({ id, name, option: optionFor(columnType), values });

describe('extractJinjaReferences', () => {
  it('pulls identifiers out of {{ }} tokens, including filters and whitespace variants', () => {
    expect(extractJinjaReferences('Write about {{ topic }} for {{audience}}')).toEqual([
      'topic',
      'audience',
    ]);
    expect(extractJinjaReferences('{{- name | upper }}')).toEqual(['name']);
    expect(extractJinjaReferences('no references here')).toEqual([]);
  });
});

describe('validateColumnName', () => {
  it('requires a non-empty valid identifier that is unique', () => {
    expect(validateColumnName('', new Set())).toMatch(/required/i);
    expect(validateColumnName('2bad', new Set())).toMatch(/letters/i);
    expect(validateColumnName('with space', new Set())).toMatch(/letters/i);
    expect(validateColumnName('topic', new Set(['topic']))).toMatch(/already exists/i);
    expect(validateColumnName('topic', new Set(['other']))).toBeNull();
  });
});

describe('defaultColumnName', () => {
  it('derives a unique name from the column type, skipping taken names', () => {
    const option = optionFor('llm-text');
    expect(defaultColumnName(option, new Set())).toBe('llm_text_1');
    expect(defaultColumnName(option, new Set(['llm_text_1']))).toBe('llm_text_2');
  });

  it('uses the sampler sub-type when present', () => {
    const option = optionFor('sampler', 'uuid');
    expect(defaultColumnName(option, new Set())).toBe('uuid_1');
  });
});

describe('buildColumnsFromTemplate', () => {
  it('resolves specs into placed columns with sequential ids and seeded values', () => {
    const columns = buildColumnsFromTemplate([
      { columnType: 'sampler', samplerType: 'category', name: 'domain' } as never,
      {
        columnType: 'llm-text',
        name: 'instruction',
        values: { prompt: 'About {{ domain }}', model_alias: 'default' },
      },
    ]);

    expect(columns.map((c) => c.id)).toEqual(['col-0', 'col-1']);
    expect(columns.map((c) => c.name)).toEqual(['domain', 'instruction']);
    expect(columns[0].option.samplerType).toBe('category');
    expect(columns[1].values).toEqual({ prompt: 'About {{ domain }}', model_alias: 'default' });
  });

  it('numbers ids from startId and skips unresolvable specs', () => {
    const columns = buildColumnsFromTemplate(
      [
        { columnType: 'not-a-type', name: 'nope' } as never,
        { columnType: 'llm-text', name: 'answer' },
      ],
      5
    );

    expect(columns).toHaveLength(1);
    expect(columns[0]).toMatchObject({ id: 'col-5', name: 'answer' });
  });
});

describe('buildGraph', () => {
  it('draws an edge only when a column references another via Jinja2', () => {
    const columns = [
      column('a', 'topic', 'seed-dataset', {}),
      column('b', 'question', 'llm-text', {
        prompt: 'Ask about {{ topic }}',
        model_alias: 'default',
      }),
    ];

    const { nodes, edges } = buildGraph(columns);

    expect(nodes).toHaveLength(2);
    expect(edges).toEqual([{ source: 'a', target: 'b' }]);
    // The dependency is surfaced as a tag on the dependent node.
    expect(nodes.find((n) => n.id === 'b')?.data.tags).toEqual(['{{topic}}']);
  });

  it('leaves unreferenced columns as independent roots', () => {
    const columns = [
      column('a', 'topic', 'seed-dataset', {}),
      column('b', 'note', 'llm-text', { prompt: 'A static prompt', model_alias: 'default' }),
    ];

    expect(buildGraph(columns).edges).toEqual([]);
  });

  it('ignores references to names that are not real columns and self-references', () => {
    const columns = [
      column('a', 'summary', 'llm-text', {
        prompt: 'Summarize {{ summary }} and {{ missing }}',
        model_alias: 'default',
      }),
    ];

    expect(buildGraph(columns).edges).toEqual([]);
  });

  it('derives edges from column-name fields (embedding target, validation targets)', () => {
    const columns = [
      column('a', 'text', 'seed-dataset', {}),
      column('b', 'other', 'seed-dataset', {}),
      column('c', 'text_vec', 'embedding', { target_column: 'text', model_alias: 'default' }),
      column('d', 'checks', 'validation', {
        target_columns: 'text, other',
        validator_type: 'code',
      }),
    ];

    const { edges } = buildGraph(columns);

    expect(edges).toContainEqual({ source: 'a', target: 'c' });
    expect(edges).toContainEqual({ source: 'a', target: 'd' });
    expect(edges).toContainEqual({ source: 'b', target: 'd' });
    expect(edges).toHaveLength(3);
  });
});

describe('palette catalog', () => {
  it('has a field descriptor path for every catalog column type', () => {
    // Sanity: findColumnOption resolves every option the palette can emit.
    for (const group of COLUMN_TYPE_GROUPS) {
      for (const option of group.options) {
        expect(
          findColumnOption({ columnType: option.columnType, samplerType: option.samplerType })
        ).toBe(option);
      }
    }
  });
});
