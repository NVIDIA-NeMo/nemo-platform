// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EvaluatorCreateTaskBody } from '@nemo/sdk/generated/evaluator/zod/evaluator-plugin-tasks-routes/evaluatorCreateTask';

export const TARGET_FORMATS = ['custom', 'agent-eval-task'] as const;

export type TargetFormat = (typeof TARGET_FORMATS)[number];

export const DEFAULT_TARGET_FORMAT: TargetFormat = 'custom';

/** 1-based row number, supplied to Handlebars as a `@data` variable by the transform and preview. */
export const ROW_NUMBER_TEMPLATE = '{{@row}}';

/** Handlebars expression that substitutes a source column, unescaped. */
export const columnTemplate = (column: string) => `{{{${column}}}}`;

export interface TargetFormatField {
  key: string;
  /** Help text shown beneath the mapping row. Prefer the generated zod describe blocks. */
  description: string;
  /** Blocks submit until the row resolves to a value. */
  required?: boolean;
  /** Prefill a mapping row for this key. Fields without it are offered as key suggestions only. */
  prefill?: boolean;
  /** Value the prefilled row starts with, given the source file's column names. */
  defaultValue?: (sourceColumns: string[]) => string;
}

export interface TargetFormatDefinition {
  value: TargetFormat;
  label: string;
  help: string;
  /** Appended to the source file's base name when suggesting an output file. */
  outputSuffix: string;
  /** Empty for free-form formats, whose keys come from the source file instead. */
  fields: TargetFormatField[];
}

/** Maps to the first candidate the source file actually has, else `fallback`. */
const firstMatchingColumn =
  (candidates: string[], fallback = '') =>
  (sourceColumns: string[]) => {
    const match = candidates.find((candidate) => sourceColumns.includes(candidate));
    return match ? columnTemplate(match) : fallback;
  };

const taskShape = EvaluatorCreateTaskBody.shape;

/**
 * `id` and `reference` have no describe block on the create-task body — `id` comes from the URL
 * path and `reference` only exists on job-inline tasks — so their help text is copied from the
 * generated `AgentEvalTaskInput` / `AgentEvalTaskInputReference` docs.
 */
const TASK_ID_DESCRIPTION = 'Stable task identifier, unique within the task collection.';
const TASK_REFERENCE_DESCRIPTION =
  "Grader-only ground truth (held-out tests, expected outputs, rubric data). Surfaced to metrics but never seeded into the agent's workspace or shown to the agent.";

const AGENT_EVAL_TASK_FIELDS: TargetFormatField[] = [
  {
    key: 'id',
    description: `Required. ${TASK_ID_DESCRIPTION} Defaults to the row number when the file has no id column.`,
    required: true,
    prefill: true,
    defaultValue: firstMatchingColumn(['id', 'task_id', 'name'], `task-${ROW_NUMBER_TEMPLATE}`),
  },
  {
    key: 'intent',
    description: `Required. ${taskShape.intent.description ?? ''}`,
    required: true,
    prefill: true,
    defaultValue: firstMatchingColumn(['intent']),
  },
  {
    key: 'inputs.instruction',
    description: taskShape.inputs.unwrap().shape.instruction.description ?? '',
    prefill: true,
    defaultValue: firstMatchingColumn(['instruction', 'prompt', 'question']),
  },
  { key: 'reference.expected', description: TASK_REFERENCE_DESCRIPTION },
  { key: 'metadata', description: taskShape.metadata.description ?? '' },
  { key: 'metrics', description: taskShape.metrics.description ?? '' },
];

export const TARGET_FORMAT_DEFINITIONS: Record<TargetFormat, TargetFormatDefinition> = {
  custom: {
    value: 'custom',
    label: 'Custom',
    help: 'Map source columns to any output keys you choose.',
    outputSuffix: 'transformed',
    fields: [],
  },
  'agent-eval-task': {
    value: 'agent-eval-task',
    label: 'Task (Evaluation)',
    help: 'Emit one agent-eval task per row, using the keys the Evaluator task API expects.',
    outputSuffix: 'tasks',
    fields: AGENT_EVAL_TASK_FIELDS,
  },
};

export const TARGET_FORMAT_OPTIONS = TARGET_FORMATS.map((value) => ({
  value,
  children: TARGET_FORMAT_DEFINITIONS[value].label,
}));

const byFormat = <T>(build: (definition: TargetFormatDefinition) => T): Record<TargetFormat, T> =>
  Object.fromEntries(
    TARGET_FORMATS.map((format) => [format, build(TARGET_FORMAT_DEFINITIONS[format])])
  ) as Record<TargetFormat, T>;

/**
 * Keys the mapping grid is seeded with. `undefined` hands the grid back to the source file's own
 * schema, which is what makes the custom format free-form.
 */
const PREFILLED_SCHEMAS = byFormat((definition) => {
  const prefilled = definition.fields.filter((field) => field.prefill);
  return prefilled.length
    ? (Object.fromEntries(prefilled.map((field) => [field.key, null])) as Record<string, unknown>)
    : undefined;
});

const KEY_SUGGESTIONS = byFormat((definition) =>
  definition.fields.length ? definition.fields.map((field) => field.key) : undefined
);

const KEY_DESCRIPTIONS = byFormat((definition) =>
  Object.fromEntries(definition.fields.map((field) => [field.key, field.description]))
);

const REQUIRED_KEYS = byFormat((definition) =>
  definition.fields.filter((field) => field.required).map((field) => field.key)
);

const FIELDS_BY_KEY = byFormat(
  (definition) => new Map(definition.fields.map((field) => [field.key, field]))
);

export const getPrefilledSchema = (format: TargetFormat) => PREFILLED_SCHEMAS[format];

export const getKeySuggestions = (format: TargetFormat) => KEY_SUGGESTIONS[format];

export const getKeyDescriptions = (format: TargetFormat) => KEY_DESCRIPTIONS[format];

export const getRequiredKeys = (format: TargetFormat) => REQUIRED_KEYS[format];

export const getTargetFormatHelp = (format: TargetFormat) => TARGET_FORMAT_DEFINITIONS[format].help;

/** The transform emits JSON Lines whatever the source file was, so the output is always `.jsonl`. */
const OUTPUT_EXTENSION = 'jsonl';

/** Suggested destination, alongside the source file rather than on top of it. */
export const getDefaultOutputFilepath = (format: TargetFormat, sourceFilepath: string) => {
  if (!sourceFilepath) return '';
  const lastSlash = sourceFilepath.lastIndexOf('/');
  const directory = sourceFilepath.slice(0, lastSlash + 1);
  const filename = sourceFilepath.slice(lastSlash + 1);
  const extension = filename.lastIndexOf('.');
  const base = extension > 0 ? filename.slice(0, extension) : filename;
  const suffix = TARGET_FORMAT_DEFINITIONS[format].outputSuffix;
  return `${directory}${base}-${suffix}.${OUTPUT_EXTENSION}`;
};

/**
 * Value a freshly seeded mapping row starts with. Keys the format does not define — every key in
 * the custom format — echo their source column, preserving the original transform behavior.
 */
export const getDefaultMappingValue = (
  format: TargetFormat,
  key: string,
  sourceColumns: string[]
) => {
  const field = FIELDS_BY_KEY[format].get(key);
  if (!field) return columnTemplate(key);
  return field.defaultValue?.(sourceColumns) ?? '';
};
