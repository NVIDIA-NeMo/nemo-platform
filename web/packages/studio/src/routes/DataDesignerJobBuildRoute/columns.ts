// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { type DataDesignerConfig, SamplerType } from '@nemo/sdk/generated/data-designer/schema';
import { COLUMN_TYPE_GROUPS } from '@studio/components/AddColumnPalette/constants';
import type {
  AddColumnSelection,
  ColumnTypeColor,
  ColumnTypeOption,
  DataDesignerColumnType,
} from '@studio/components/AddColumnPalette/types';
import type { TemplateColumnSpec } from '@studio/components/CreateFilesetStart/types';
import type { DagEdge, DagNode } from '@studio/components/DagCanvas/types';
import {
  type BuilderModel,
  buildModelConfigs,
} from '@studio/routes/DataDesignerJobBuildRoute/models';

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
  /**
   * Serialize the value as a comma-separated list (e.g. sampler category values). Unlike
   * `reference: 'list'`, this does not treat the entries as column names / dependencies.
   */
  list?: boolean;
  /**
   * How to coerce the string form value when serializing to the SDK config. Defaults to a
   * plain string; `number`/`boolean` parse the value, `json` parses an object/array literal.
   * Used by sampler params whose SDK types are non-string (see PARAM_FIELDS_BY_SAMPLER_TYPE).
   */
  valueType?: 'number' | 'boolean' | 'json';
}

/** Not yet the SDK column config — that's produced by {@link buildDataDesignerConfig}. */
export interface BuilderColumn {
  /** Canvas-unique id (also the DAG node id). */
  id: string;
  option: ColumnTypeOption;
  name: string;
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
  // Shared across all sampler sub-types, emitted at the top level of the sampler config.
  // Sub-type-specific fields (collected into `params`) come from PARAM_FIELDS_BY_SAMPLER_TYPE.
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

const BOOL_OPTIONS = [
  { label: 'Yes', value: 'true' },
  { label: 'No', value: 'false' },
] as const;

const PARAM_FIELDS_BY_SAMPLER_TYPE: Partial<Record<SamplerType, ColumnField[]>> = {
  [SamplerType.uuid]: [
    {
      key: 'prefix',
      label: 'Prefix (optional)',
      kind: 'text',
      placeholder: 'e.g. user-',
      helperText: 'Prepended to each generated UUID.',
    },
    {
      key: 'short_form',
      label: 'Short form (optional)',
      kind: 'select',
      valueType: 'boolean',
      options: BOOL_OPTIONS,
      helperText: 'Truncate UUIDs to 8 characters.',
    },
    {
      key: 'uppercase',
      label: 'Uppercase (optional)',
      kind: 'select',
      valueType: 'boolean',
      options: BOOL_OPTIONS,
      helperText: 'Capitalize all letters in the UUID.',
    },
  ],
  [SamplerType.category]: [
    {
      key: 'values',
      label: 'Categories',
      kind: 'textarea',
      required: true,
      list: true,
      placeholder: 'science, technology, history, arts, business',
      helperText: 'Comma-separated values to sample from.',
    },
  ],
  [SamplerType.subcategory]: [
    {
      key: 'category',
      label: 'Parent category column',
      kind: 'text',
      required: true,
      reference: 'single',
      placeholder: 'Name of the parent category column',
      helperText: 'The category column each subcategory value depends on.',
    },
    {
      key: 'values',
      label: 'Subcategory values (JSON)',
      kind: 'textarea',
      required: true,
      valueType: 'json',
      placeholder: '{ "science": ["physics", "chemistry"], "arts": ["music", "film"] }',
      helperText: 'JSON mapping each parent value to a list of subcategory values.',
    },
  ],
  [SamplerType.uniform]: [
    {
      key: 'low',
      label: 'Low',
      kind: 'text',
      required: true,
      valueType: 'number',
      helperText: 'Lower bound of the range (inclusive).',
    },
    {
      key: 'high',
      label: 'High',
      kind: 'text',
      required: true,
      valueType: 'number',
      helperText: 'Upper bound of the range (must be greater than low).',
    },
    {
      key: 'decimal_places',
      label: 'Decimal places (optional)',
      kind: 'text',
      valueType: 'number',
      helperText: 'Round sampled values to this many decimals.',
    },
  ],
  [SamplerType.gaussian]: [
    { key: 'mean', label: 'Mean', kind: 'text', required: true, valueType: 'number' },
    {
      key: 'stddev',
      label: 'Standard deviation',
      kind: 'text',
      required: true,
      valueType: 'number',
      helperText: 'Must be positive.',
    },
    {
      key: 'decimal_places',
      label: 'Decimal places (optional)',
      kind: 'text',
      valueType: 'number',
      helperText: 'Round sampled values to this many decimals.',
    },
  ],
  [SamplerType.bernoulli]: [
    {
      key: 'p',
      label: 'Probability of success (p)',
      kind: 'text',
      required: true,
      valueType: 'number',
      helperText: 'Between 0 and 1.',
    },
  ],
  [SamplerType.bernoulli_mixture]: [
    {
      key: 'p',
      label: 'Mixture probability (p)',
      kind: 'text',
      required: true,
      valueType: 'number',
      helperText: 'Between 0 and 1; otherwise the sample is 0.',
    },
    {
      key: 'dist_name',
      label: 'Distribution name',
      kind: 'text',
      required: true,
      placeholder: 'e.g. norm, gamma, expon',
      helperText: 'A scipy.stats distribution name.',
    },
    {
      key: 'dist_params',
      label: 'Distribution params (JSON)',
      kind: 'textarea',
      required: true,
      valueType: 'json',
      placeholder: '{ "loc": 0, "scale": 1 }',
      helperText: 'JSON parameters for the distribution.',
    },
  ],
  [SamplerType.binomial]: [
    {
      key: 'n',
      label: 'Number of trials (n)',
      kind: 'text',
      required: true,
      valueType: 'number',
      helperText: 'Positive integer.',
    },
    {
      key: 'p',
      label: 'Probability of success (p)',
      kind: 'text',
      required: true,
      valueType: 'number',
      helperText: 'Between 0 and 1.',
    },
  ],
  [SamplerType.poisson]: [
    {
      key: 'mean',
      label: 'Mean (rate λ)',
      kind: 'text',
      required: true,
      valueType: 'number',
      helperText: 'Must be positive.',
    },
  ],
  [SamplerType.scipy]: [
    {
      key: 'dist_name',
      label: 'Distribution name',
      kind: 'text',
      required: true,
      placeholder: 'e.g. beta, gamma, lognorm',
      helperText: 'A scipy.stats distribution name.',
    },
    {
      key: 'dist_params',
      label: 'Distribution params (JSON)',
      kind: 'textarea',
      required: true,
      valueType: 'json',
      placeholder: '{ "a": 2, "b": 5 }',
      helperText: 'JSON parameters for the distribution.',
    },
    {
      key: 'decimal_places',
      label: 'Decimal places (optional)',
      kind: 'text',
      valueType: 'number',
      helperText: 'Round sampled values to this many decimals.',
    },
  ],
  [SamplerType.person]: [
    {
      key: 'locale',
      label: 'Locale (optional)',
      kind: 'text',
      placeholder: 'e.g. en_US',
      helperText: 'Managed persona locale (e.g. en_US, ja_JP).',
    },
    { key: 'sex', label: 'Sex (optional)', kind: 'select', options: asOptions(['Male', 'Female']) },
    {
      key: 'city',
      label: 'Cities (optional)',
      kind: 'text',
      list: true,
      placeholder: 'comma,separated,cities',
      helperText: 'Comma-separated city filter.',
    },
    {
      key: 'with_synthetic_personas',
      label: 'Synthetic personas (optional)',
      kind: 'select',
      valueType: 'boolean',
      options: BOOL_OPTIONS,
      helperText: 'Append persona trait columns to each person.',
    },
  ],
  [SamplerType.datetime]: [
    {
      key: 'start',
      label: 'Start',
      kind: 'text',
      required: true,
      placeholder: 'e.g. 2020-01-01',
      helperText: 'Earliest datetime (inclusive).',
    },
    {
      key: 'end',
      label: 'End',
      kind: 'text',
      required: true,
      placeholder: 'e.g. 2025-01-01',
      helperText: 'Exclusive upper bound.',
    },
    {
      key: 'unit',
      label: 'Unit (optional)',
      kind: 'select',
      options: asOptions(['Y', 'M', 'D', 'h', 'm', 's']),
      helperText: 'Sampling granularity (defaults to days).',
    },
  ],
  [SamplerType.timedelta]: [
    {
      key: 'dt_min',
      label: 'Minimum delta',
      kind: 'text',
      required: true,
      valueType: 'number',
      helperText: 'Non-negative and less than the maximum.',
    },
    {
      key: 'dt_max',
      label: 'Maximum delta',
      kind: 'text',
      required: true,
      valueType: 'number',
      helperText: 'Greater than the minimum.',
    },
    {
      key: 'reference_column_name',
      label: 'Reference datetime column',
      kind: 'text',
      required: true,
      reference: 'single',
      placeholder: 'Name of an existing datetime column',
      helperText: 'The datetime column each delta is added to.',
    },
    {
      key: 'unit',
      label: 'Unit (optional)',
      kind: 'select',
      options: asOptions(['D', 'h', 'm', 's']),
      helperText: 'Time unit for the deltas (defaults to days).',
    },
  ],
};

/** The sampler `params` fields for a sampler sub-type (empty for sub-types without any). */
const getSamplerParamFields = (samplerType: SamplerType | undefined): ColumnField[] =>
  samplerType ? (PARAM_FIELDS_BY_SAMPLER_TYPE[samplerType] ?? []) : [];

export const getColumnFields = (
  option: Pick<ColumnTypeOption, 'columnType' | 'samplerType'>
): ColumnField[] => {
  const { columnType, samplerType } = option;
  if (!columnType) return [];
  const base = FIELDS_BY_COLUMN_TYPE[columnType] ?? [];
  if (columnType === 'sampler') return [...getSamplerParamFields(samplerType), ...base];
  return base;
};

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

// Specs whose column type can't be matched in the palette are silently skipped.
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

const columnDependencies = (column: BuilderColumn, knownNames: Set<string>): Set<string> => {
  const deps = new Set<string>();
  const add = (candidate: string) => {
    const name = candidate.trim();
    if (name && name !== column.name && knownNames.has(name)) deps.add(name);
  };
  for (const field of getColumnFields(column.option)) {
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

const isValidJson = (value: string): boolean => {
  try {
    JSON.parse(value);
    return true;
  } catch {
    return false;
  }
};

export const validateColumns = (columns: BuilderColumn[]): string[] => {
  if (columns.length === 0) return ['Add at least one column before creating the job.'];

  const errors: string[] = [];
  for (const column of columns) {
    const label = column.name || column.option.label;
    const takenNames = new Set(
      columns.filter((other) => other.id !== column.id).map((other) => other.name)
    );
    const nameError = validateColumnName(column.name, takenNames);
    if (nameError) errors.push(`${label}: ${nameError}`);

    for (const field of getColumnFields(column.option)) {
      const value = column.values[field.key]?.trim();
      if (field.required && !value) {
        errors.push(`${label}: ${field.label} is required.`);
        continue;
      }
      if (!value) continue;
      if (field.key === 'output_format' && !isValidJson(value)) {
        errors.push(`${label}: ${field.label} must be valid JSON.`);
      }
      if (field.valueType === 'number' && !Number.isFinite(Number(value))) {
        errors.push(`${label}: ${field.label} must be a number.`);
      }
      if (field.valueType === 'json' && !isValidJson(value)) {
        errors.push(`${label}: ${field.label} must be valid JSON.`);
      }
    }
  }
  return errors;
};

/** Splits a comma-separated field value into trimmed, non-empty entries. */
const splitList = (value: string): string[] =>
  value
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);

/** Coerces a (non-empty) string field value into its SDK config form per {@link ColumnField}. */
const serializeFieldValue = (field: ColumnField, value: string): unknown => {
  if (field.list) return splitList(value);
  switch (field.valueType) {
    case 'number':
      return Number(value);
    case 'boolean':
      return value === 'true';
    case 'json':
      return JSON.parse(value);
    default:
      return value;
  }
};

/**
 * Converts a sampler column into the SDK's `SamplerColumnConfig` shape. Sub-type params
 * are nested under the required `params` object; `convert_to` stays at the top level.
 */
const toSamplerConfig = (column: BuilderColumn): Record<string, unknown> => {
  const params: Record<string, unknown> = {};
  for (const field of getSamplerParamFields(column.option.samplerType)) {
    const value = column.values[field.key]?.trim();
    if (!value) continue;
    params[field.key] = serializeFieldValue(field, value);
  }

  const config: Record<string, unknown> = {
    name: column.name,
    column_type: 'sampler',
    sampler_type: column.option.samplerType,
    params,
  };
  const convertTo = column.values.convert_to?.trim();
  if (convertTo) config.convert_to = convertTo;
  return config;
};

const toColumnConfig = (column: BuilderColumn): Record<string, unknown> => {
  if (column.option.columnType === 'sampler') return toSamplerConfig(column);

  const config: Record<string, unknown> = {
    name: column.name,
    column_type: column.option.columnType,
  };

  for (const field of getColumnFields(column.option)) {
    const value = column.values[field.key]?.trim();
    if (!value) continue;
    if (field.key === 'output_format') {
      config[field.key] = JSON.parse(value);
    } else if (field.reference === 'list' || field.list) {
      config[field.key] = splitList(value);
    } else {
      config[field.key] = value;
    }
  }
  return config;
};

export const buildDataDesignerConfig = (
  columns: BuilderColumn[],
  models: BuilderModel[] = []
): DataDesignerConfig => {
  const config: DataDesignerConfig = {
    columns: columns.map(toColumnConfig) as unknown as DataDesignerConfig['columns'],
  };
  const modelConfigs = buildModelConfigs(models);
  if (modelConfigs) config.model_configs = modelConfigs;
  return config;
};
