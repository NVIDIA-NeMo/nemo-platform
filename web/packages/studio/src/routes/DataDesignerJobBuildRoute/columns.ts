// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { COLUMN_TYPE_GROUPS } from '@studio/components/AddColumnPalette/constants';
import type {
  AddColumnSelection,
  ColumnTypeColor,
  ColumnTypeOption,
  DataDesignerColumnType,
} from '@studio/components/AddColumnPalette/types';
import type { TemplateColumnSpec } from '@studio/components/CreateFilesetStart/types';
import type { DagEdge, DagNode } from '@studio/components/DagCanvas/types';

export type FieldReference =
  /** Value is a Jinja2 template; `{{ column_name }}` tokens are dependencies. */
  | 'jinja'
  /** Value is a single column name. */
  | 'single'
  /** Value is a comma-separated list of column names. */
  | 'list';

export type FieldKind = 'text' | 'textarea' | 'select';

export interface ColumnField {
  /** Key into {@link BuilderColumn.values} and the eventual SDK config. */
  key: string;
  label: string;
  kind: FieldKind;
  required?: boolean;
  placeholder?: string;
  helperText?: string;
  options?: readonly { label: string; value: string }[];
  /** If set, values in this field create dependency edges to other columns. */
  reference?: FieldReference;
}

/**
 * A column the user has added to the canvas: the picked catalog option plus the values
 * entered in the config modal. `name` is the column's identifier — other columns
 * reference it via `{{ name }}`. Not yet the SDK column config.
 */
export interface BuilderColumn {
  /** Canvas-unique id (also the DAG node id). */
  id: string;
  option: ColumnTypeOption;
  /** The column name (Jinja2 identifier other columns can reference). */
  name: string;
  /** Field values keyed by {@link ColumnField.key}. */
  values: Record<string, string>;
}

const CODE_LANGS = [
  'python',
  'javascript',
  'typescript',
  'java',
  'kotlin',
  'go',
  'rust',
  'ruby',
  'scala',
  'swift',
  'c',
  'cpp',
  'csharp',
  'bash',
  'sql:sqlite',
  'sql:postgres',
  'sql:mysql',
  'sql:tsql',
  'sql:bigquery',
  'sql:ansi',
] as const;

const asOptions = (values: readonly string[]) => values.map((value) => ({ label: value, value }));

const PROMPT_FIELD: ColumnField = {
  key: 'prompt',
  label: 'Prompt',
  kind: 'textarea',
  required: true,
  reference: 'jinja',
  placeholder: 'Write a question about {{ topic }} at {{ difficulty }} difficulty.',
  helperText: 'Jinja2 template — reference other columns with {{ column_name }}.',
};

const MODEL_ALIAS_FIELD: ColumnField = {
  key: 'model_alias',
  label: 'Model alias',
  kind: 'text',
  required: true,
  placeholder: 'e.g. default',
  helperText: 'Alias of a configured model to generate with.',
};

const SYSTEM_PROMPT_FIELD: ColumnField = {
  key: 'system_prompt',
  label: 'System prompt (optional)',
  kind: 'textarea',
  reference: 'jinja',
  helperText: 'Optional. Also supports {{ column_name }} references.',
};

/**
 * The user-editable fields for a column type, in display order. `name` is handled
 * separately by the modal (every column has one), so it is not included here.
 */
const FIELDS_BY_COLUMN_TYPE: Record<NonNullable<DataDesignerColumnType>, ColumnField[]> = {
  'llm-text': [PROMPT_FIELD, MODEL_ALIAS_FIELD, SYSTEM_PROMPT_FIELD],
  'llm-code': [
    PROMPT_FIELD,
    MODEL_ALIAS_FIELD,
    {
      key: 'code_lang',
      label: 'Language',
      kind: 'select',
      required: true,
      options: asOptions(CODE_LANGS),
    },
    SYSTEM_PROMPT_FIELD,
  ],
  'llm-structured': [
    PROMPT_FIELD,
    MODEL_ALIAS_FIELD,
    {
      key: 'output_format',
      label: 'Output schema (JSON)',
      kind: 'textarea',
      required: true,
      placeholder: '{ "type": "object", "properties": { ... } }',
      helperText: 'JSON schema describing the structured output.',
    },
    SYSTEM_PROMPT_FIELD,
  ],
  'llm-judge': [PROMPT_FIELD, MODEL_ALIAS_FIELD, SYSTEM_PROMPT_FIELD],
  image: [
    { ...PROMPT_FIELD, placeholder: 'Generate an image of {{ subject }}.' },
    MODEL_ALIAS_FIELD,
  ],
  embedding: [
    {
      key: 'target_column',
      label: 'Target column',
      kind: 'text',
      required: true,
      reference: 'single',
      placeholder: 'Name of the column to embed',
      helperText: 'The text column whose values are embedded.',
    },
    MODEL_ALIAS_FIELD,
  ],
  expression: [
    {
      key: 'expr',
      label: 'Expression',
      kind: 'textarea',
      required: true,
      reference: 'jinja',
      placeholder: '{{ first_name }} {{ last_name }}',
      helperText: 'Jinja2 expression evaluated per row; reference columns with {{ }}.',
    },
    {
      key: 'dtype',
      label: 'Result type',
      kind: 'select',
      options: asOptions(['str', 'int', 'float', 'bool']),
      helperText: 'Type to cast the result to (defaults to str).',
    },
  ],
  validation: [
    {
      key: 'target_columns',
      label: 'Target columns',
      kind: 'text',
      required: true,
      reference: 'list',
      placeholder: 'comma,separated,column,names',
      helperText: 'Comma-separated column names to validate.',
    },
    {
      key: 'validator_type',
      label: 'Validator',
      kind: 'select',
      required: true,
      options: asOptions(['code', 'local_callable', 'remote']),
    },
  ],
  'seed-dataset': [],
  custom: [
    {
      key: 'generation_strategy',
      label: 'Generation strategy',
      kind: 'select',
      options: asOptions(['cell_by_cell', 'full_column']),
    },
  ],
  sampler: [
    {
      key: 'convert_to',
      label: 'Convert to (optional)',
      kind: 'text',
      placeholder: 'e.g. int, float, or %Y-%m-%d',
      helperText: 'Optional type conversion applied after sampling.',
    },
  ],
};

export const getColumnFields = (columnType: DataDesignerColumnType): ColumnField[] =>
  columnType ? (FIELDS_BY_COLUMN_TYPE[columnType] ?? []) : [];

/** Accent color → NVIDIA Foundations text token, matching `CardNode`'s idle styling. */
const ACCENT_VAR_CLASS: Record<ColumnTypeColor, string> = {
  blue: 'text-[color:var(--text-color-accent-blue)]',
  gray: 'text-[color:var(--text-color-accent-gray)]',
  green: 'text-[color:var(--text-color-accent-green)]',
  purple: 'text-[color:var(--text-color-accent-purple)]',
  red: 'text-[color:var(--text-color-accent-red)]',
  teal: 'text-[color:var(--text-color-accent-teal)]',
  yellow: 'text-[color:var(--text-color-accent-yellow)]',
};

/**
 * Resolves an {@link AddColumnSelection} (fired by the palette) to its full catalog
 * option. Matches on `column_type`, and additionally on `sampler_type` for samplers.
 */
export const findColumnOption = (selection: AddColumnSelection): ColumnTypeOption | undefined => {
  for (const group of COLUMN_TYPE_GROUPS) {
    const match = group.options.find(
      (option) =>
        option.columnType === selection.columnType && option.samplerType === selection.samplerType
    );
    if (match) return match;
  }
  return undefined;
};

/**
 * Resolves a template's column specs into placed {@link BuilderColumn}s, numbering ids
 * from `startId` (so subsequent user-added columns can continue from the returned count).
 * Specs whose column type can't be matched in the palette are skipped.
 */
export const buildColumnsFromTemplate = (
  specs: readonly TemplateColumnSpec[],
  startId = 0
): BuilderColumn[] => {
  const columns: BuilderColumn[] = [];
  let nextId = startId;
  for (const spec of specs) {
    const option = findColumnOption(spec);
    if (!option) continue;
    columns.push({ id: `col-${nextId++}`, option, name: spec.name, values: { ...spec.values } });
  }
  return columns;
};

const JINJA_REF = /\{\{-?\s*([a-zA-Z_][a-zA-Z0-9_]*)/g;

export const extractJinjaReferences = (text: string): string[] => {
  const refs: string[] = [];
  for (const match of text.matchAll(JINJA_REF)) refs.push(match[1]);
  return refs;
};

/**
 * The names of columns this column depends on, resolved against the set of known column
 * names. Combines Jinja2 template references (prompt, expr, …) with explicit column-name
 * fields (embedding target, validation targets). Self-references are ignored.
 */
const columnDependencies = (column: BuilderColumn, knownNames: Set<string>): Set<string> => {
  const deps = new Set<string>();
  const add = (candidate: string) => {
    const name = candidate.trim();
    if (name && name !== column.name && knownNames.has(name)) deps.add(name);
  };
  for (const field of getColumnFields(column.option.columnType)) {
    const value = column.values[field.key]?.trim();
    if (!value) continue;
    switch (field.reference) {
      case 'jinja':
        extractJinjaReferences(value).forEach(add);
        break;
      case 'single':
        add(value);
        break;
      case 'list':
        value.split(',').forEach(add);
        break;
    }
  }
  return deps;
};

/**
 * Builds the DAG from the current columns. Nodes carry the column name/type for display;
 * edges are drawn only where one column references another (via Jinja2 `{{ }}` or a
 * column-name field), so unconnected columns render as independent roots.
 */
export const buildGraph = (columns: BuilderColumn[]): { nodes: DagNode[]; edges: DagEdge[] } => {
  const knownNames = new Set(columns.map((column) => column.name).filter(Boolean));
  const idByName = new Map(columns.filter((c) => c.name).map((c) => [c.name, c.id]));

  const nodes: DagNode[] = [];
  const edges: DagEdge[] = [];

  for (const column of columns) {
    const { option } = column;
    const deps = columnDependencies(column, knownNames);
    nodes.push({
      id: column.id,
      data: {
        title: column.name || option.label,
        type: (option.columnType ?? '').replace(/-/g, ' ').toUpperCase(),
        description: option.description,
        icon: option.icon,
        colorClassName: ACCENT_VAR_CLASS[option.color],
        tags: [...deps].map((name) => `{{${name}}}`),
      },
    });
    for (const dep of deps) {
      const source = idByName.get(dep);
      if (source && source !== column.id) edges.push({ source, target: column.id });
    }
  }

  return { nodes, edges };
};

/**
 * A default, unique column name for a freshly added column, derived from its type
 * (e.g. `llm_text_1`). Ensures the new column is immediately referenceable and never
 * collides with an existing name.
 */
export const defaultColumnName = (option: ColumnTypeOption, takenNames: Set<string>): string => {
  const base = (option.samplerType ?? option.columnType ?? 'column').replace(/[^a-zA-Z0-9]+/g, '_');
  for (let n = 1; ; n++) {
    const candidate = `${base}_${n}`;
    if (!takenNames.has(candidate)) return candidate;
  }
};

export const validateColumnName = (name: string, takenNames: Set<string>): string | null => {
  const trimmed = name.trim();
  if (!trimmed) return 'Name is required.';
  if (!/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(trimmed)) {
    return 'Use letters, numbers, and underscores; must not start with a number.';
  }
  if (takenNames.has(trimmed)) return 'A column with this name already exists.';
  return null;
};
