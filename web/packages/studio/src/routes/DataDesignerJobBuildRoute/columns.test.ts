// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SamplerType } from '@nemo/sdk/generated/data-designer/schema';
import { COLUMN_TYPE_GROUPS } from '@studio/components/AddColumnPalette/constants';
import type { ColumnTypeOption } from '@studio/components/AddColumnPalette/types';
import { FILESET_TEMPLATES } from '@studio/components/CreateFilesetStart/templates';
import {
  type BuilderColumn,
  buildColumnsFromTemplate,
  buildDataDesignerConfig,
  buildGraph,
  defaultColumnName,
  extractJinjaReferences,
  findColumnOption,
  validateColumnName,
  validateColumns,
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
  values: Record<string, string>,
  samplerType?: string
): BuilderColumn => ({ id, name, option: optionFor(columnType, samplerType), values });

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

describe('sampler columns', () => {
  it('nests category values under the required params object', () => {
    const columns = [
      column('a', 'domain', 'sampler', { values: 'science, history, , arts' }, 'category'),
    ];

    expect(buildDataDesignerConfig(columns).columns[0]).toEqual({
      name: 'domain',
      column_type: 'sampler',
      sampler_type: 'category',
      params: { values: ['science', 'history', 'arts'] },
    });
  });

  it('keeps convert_to at the top level alongside params', () => {
    const columns = [
      column('a', 'domain', 'sampler', { values: 'a, b', convert_to: 'str' }, 'category'),
    ];

    expect(buildDataDesignerConfig(columns).columns[0]).toMatchObject({
      params: { values: ['a', 'b'] },
      convert_to: 'str',
    });
  });

  it('requires category values', () => {
    const columns = [column('a', 'domain', 'sampler', {}, 'category')];

    expect(validateColumns(columns)).toContainEqual(expect.stringContaining('Categories'));
  });

  it('coerces numeric sampler params to numbers', () => {
    const columns = [
      column(
        'a',
        'score',
        'sampler',
        { mean: '1.5', stddev: '0.25', decimal_places: '2' },
        'gaussian'
      ),
    ];

    expect(buildDataDesignerConfig(columns).columns[0]).toEqual({
      name: 'score',
      column_type: 'sampler',
      sampler_type: 'gaussian',
      params: { mean: 1.5, stddev: 0.25, decimal_places: 2 },
    });
  });

  it('serializes boolean switches and a numeric weight list', () => {
    const uuid = column('a', 'id', 'sampler', { short_form: 'true', uppercase: 'false' }, 'uuid');
    const category = column(
      'b',
      'domain',
      'sampler',
      { values: 'a, b, c', weights: '3, 1, 1' },
      'category'
    );

    const built = buildDataDesignerConfig([uuid, category]).columns;
    expect(built[0]).toMatchObject({ params: { short_form: 'true', uppercase: 'false' } });
    expect(built[1]).toMatchObject({ params: { values: ['a', 'b', 'c'], weights: [3, 1, 1] } });
  });

  it('parses JSON sampler params (subcategory mapping)', () => {
    const columns = [
      column(
        'a',
        'sub',
        'sampler',
        { category: 'domain', values: '{ "sci": ["physics"], "art": ["music"] }' },
        'subcategory'
      ),
    ];

    expect(buildDataDesignerConfig(columns).columns[0]).toMatchObject({
      params: { category: 'domain', values: { sci: ['physics'], art: ['music'] } },
    });
  });

  it('draws edges from sampler column-name references (subcategory parent, timedelta reference)', () => {
    const columns = [
      column('a', 'domain', 'sampler', { values: 'x, y' }, 'category'),
      column(
        'b',
        'sub',
        'sampler',
        { category: 'domain', values: '{ "x": ["x1"] }' },
        'subcategory'
      ),
      column('c', 'created', 'sampler', { start: '2020-01-01', end: '2024-01-01' }, 'datetime'),
      column(
        'd',
        'shipped',
        'sampler',
        { dt_min: '1', dt_max: '30', reference_column_name: 'created' },
        'timedelta'
      ),
    ];

    const { edges } = buildGraph(columns);
    expect(edges).toContainEqual({ source: 'a', target: 'b' });
    expect(edges).toContainEqual({ source: 'c', target: 'd' });
  });

  it('flags malformed numeric and JSON sampler params', () => {
    const badNumber = column('a', 'x', 'sampler', { p: 'not-a-number' }, 'bernoulli');
    const badJson = column(
      'b',
      'y',
      'sampler',
      { dist_name: 'beta', dist_params: '{ oops' },
      'scipy'
    );

    expect(validateColumns([badNumber])).toContainEqual(
      expect.stringContaining('must be a number')
    );
    expect(validateColumns([badJson])).toContainEqual(
      expect.stringContaining('must be valid JSON')
    );
  });

  it('accepts a fully-specified numeric sampler as submittable', () => {
    const columns = [column('a', 'trials', 'sampler', { n: '10', p: '0.5' }, 'binomial')];

    expect(validateColumns(columns)).toEqual([]);
  });
});

describe('sampler-showcase template', () => {
  const showcase = FILESET_TEMPLATES.find((t) => t.id === 'sampler-showcase');
  if (!showcase) throw new Error('sampler-showcase template is missing');

  it('covers every previewable sampler sub-type in the palette', () => {
    // The managed `person` sampler is intentionally excluded — it needs downloaded
    // Nemotron Personas datasets and can't preview without them.
    const excluded = new Set<string | undefined>([SamplerType.person]);
    const samplerTypesInPalette = COLUMN_TYPE_GROUPS.flatMap((g) => g.options)
      .filter((o) => o.columnType === 'sampler')
      .map((o) => o.samplerType)
      .filter((t) => !excluded.has(t));
    const covered = new Set(showcase.columns.map((c) => c.samplerType));
    for (const samplerType of samplerTypesInPalette) {
      expect(covered).toContain(samplerType);
    }
    expect(covered.has(SamplerType.person)).toBe(false);
  });

  it('validates clean and builds a config for every sampler', () => {
    const columns = buildColumnsFromTemplate(showcase.columns);
    expect(columns).toHaveLength(showcase.columns.length);
    expect(validateColumns(columns)).toEqual([]);

    const built = buildDataDesignerConfig(columns).columns;
    // Every emitted config is a sampler with a params object.
    for (const config of built) {
      expect(config).toMatchObject({ column_type: 'sampler' });
      expect((config as { params?: unknown }).params).toBeTypeOf('object');
    }
  });

  it('wires the two intended sampler dependency edges', () => {
    const columns = buildColumnsFromTemplate(showcase.columns);
    const { edges } = buildGraph(columns);
    const idOf = (name: string) => columns.find((c) => c.name === name)?.id;

    expect(edges).toContainEqual({
      source: idOf('category_topic'),
      target: idOf('subcategory_topic'),
    });
    expect(edges).toContainEqual({ source: idOf('created_at'), target: idOf('shipped_after') });
  });

  it('coerces representative params to their SDK types', () => {
    const columns = buildColumnsFromTemplate(showcase.columns);
    const built = buildDataDesignerConfig(columns).columns as unknown as Array<{
      sampler_type: string;
      params: Record<string, unknown>;
    }>;
    const paramsFor = (t: SamplerType) => built.find((c) => c.sampler_type === t)?.params;

    expect(paramsFor(SamplerType.uuid)).toMatchObject({ short_form: 'true', uppercase: 'false' });
    expect(paramsFor(SamplerType.category)).toMatchObject({ weights: [3, 2, 1] });
    expect(paramsFor(SamplerType.binomial)).toMatchObject({ n: 10, p: 0.5 });
    expect(paramsFor(SamplerType.scipy)).toMatchObject({ dist_params: { a: 2, b: 5 } });
    expect(paramsFor(SamplerType.timedelta)).toMatchObject({ dt_min: 1, dt_max: 30 });
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
