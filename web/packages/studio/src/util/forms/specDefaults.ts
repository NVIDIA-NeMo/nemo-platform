// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  type AutomodelJobInput,
  type RlJobInput,
  type UnslothJobInput,
} from '@nemo/sdk/generated/customizer/schema';
import { CustomizationCreateAutomodelJobBody } from '@nemo/sdk/generated/customizer/zod/automodel-jobs';
import { CustomizationCreateRlJobBody } from '@nemo/sdk/generated/customizer/zod/rl-jobs';
import { CustomizationCreateUnslothJobBody } from '@nemo/sdk/generated/customizer/zod/unsloth-jobs';

/**
 * Backend defaults, read by parsing the generated Zod schemas — which carry the spec's
 * `default:` values — rather than restating them here. A field the spec leaves without a
 * default parses to `undefined`, and the form renders it unset.
 *
 * Zod fills a nested object's defaults only when that object is present, so every container
 * the form binds to is seeded with `{}`.
 */
export const AUTOMODEL_SEED = {
  model: '',
  dataset: { training: '' },
  training: { lora: {} },
  schedule: {},
  batch: {},
  optimizer: {},
  parallelism: {},
};

export const UNSLOTH_SEED = {
  model: { name: '' },
  dataset: { path: '' },
  training: { lora: {} },
  schedule: {},
  batch: {},
  optimizer: {},
  hardware: {},
};

/** `training` is a discriminated union, and the arms differ — DPO's KL penalty is 0.05, GRPO's 0. */
export const rlSeed = (type: 'dpo' | 'grpo') => ({
  model: '',
  dataset: '',
  training: { type, parallelism: {}, ...(type === 'grpo' ? { lora: {} } : {}) },
  // Bound by RlIntegrationsSection. Present so Zod fills any default the spec declares
  // inside them; without the container, nested defaults are skipped silently.
  integrations: { wandb: {}, mlflow: {} },
});

const specOf = <T>(schema: { parse: (input: unknown) => { spec: T } }, seed: unknown): T =>
  schema.parse({ spec: seed }).spec;

/** Fully-defaulted spec objects. Bind forms to these directly. */
export const AUTOMODEL_DEFAULT_SPEC = specOf<AutomodelJobInput>(
  CustomizationCreateAutomodelJobBody,
  AUTOMODEL_SEED
);
export const UNSLOTH_DEFAULT_SPEC = specOf<UnslothJobInput>(
  CustomizationCreateUnslothJobBody,
  UNSLOTH_SEED
);
export const RL_DPO_DEFAULT_SPEC = specOf<RlJobInput>(CustomizationCreateRlJobBody, rlSeed('dpo'));
export const RL_GRPO_DEFAULT_SPEC = specOf<RlJobInput>(
  CustomizationCreateRlJobBody,
  rlSeed('grpo')
);

/** Flattened `snake_case` view of a parsed spec, e.g. `optimizer_learning_rate`. */
const flatten = (
  value: unknown,
  prefix = '',
  out = new Map<string, unknown>()
): ReadonlyMap<string, unknown> => {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return out;
  for (const [key, child] of Object.entries(value)) {
    const path = prefix ? `${prefix}_${key}` : key;
    out.set(path, child);
    if (child !== null && typeof child === 'object' && !Array.isArray(child)) {
      flatten(child, path, out);
    }
  }
  return out;
};

export const AUTOMODEL_SPEC_DEFAULTS = flatten(AUTOMODEL_DEFAULT_SPEC);
export const UNSLOTH_SPEC_DEFAULTS = flatten(UNSLOTH_DEFAULT_SPEC);
/** Keyed off `training`, so callers use `epochs` / `parallelism_num_nodes`. */
export const DPO_SPEC_DEFAULTS = flatten(RL_DPO_DEFAULT_SPEC.training);
export const GRPO_SPEC_DEFAULTS = flatten(RL_GRPO_DEFAULT_SPEC.training);

/** Reads a spec default, narrowed to the type the caller expects. `undefined` means unset. */
const reader =
  <T>(guard: (value: unknown) => value is T) =>
  (defaults: ReadonlyMap<string, unknown>, field: string): T | undefined => {
    const value = defaults.get(field);
    return guard(value) ? value : undefined;
  };

const isNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value);
const isBoolean = (value: unknown): value is boolean => typeof value === 'boolean';
const isString = (value: unknown): value is string => typeof value === 'string';

export const numberDefault = reader(isNumber);
export const booleanDefault = reader(isBoolean);
export const stringDefault = reader(isString);

/** Shown when the spec gives a control no default. */
export const UNSET_PLACEHOLDER = 'Unset';

/** The backend's default when the spec has one, `Unset` when it does not. */
export const placeholderFor = (defaults: ReadonlyMap<string, unknown>, field: string): string => {
  const value = defaults.get(field);
  return value === undefined || value === null ? UNSET_PLACEHOLDER : String(value);
};

/** Spread onto a slider so its value and placeholder cannot come from different fields. */
export const specSliderProps = (
  defaults: ReadonlyMap<string, unknown>,
  field: string
): { defaultValue: number | undefined; unsetPlaceholder: string } => ({
  defaultValue: numberDefault(defaults, field),
  unsetPlaceholder: placeholderFor(defaults, field),
});
