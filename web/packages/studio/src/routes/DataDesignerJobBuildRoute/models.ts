// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import type {
  ChatCompletionInferenceParams,
  ModelConfig,
} from '@nemo/sdk/generated/data-designer/schema';
import type { InferenceParams } from '@nemo/sdk/generated/platform/schema';
import type { TemplateModelSpec } from '@studio/components/CreateFilesetStart/types';

/**
 * A model config the user has added in the builder. Mirrors the SDK {@link ModelConfig}
 * shape: `model` is the platform model URN picked in the `ModelSelectV2` dropdown and
 * `inferenceParams` holds the values edited in its params popover. `alias` is the
 * identifier a column's `model_alias` field references to generate with this model.
 */
export interface BuilderModel {
  /** Builder-unique id (stable across alias edits, used for selection). */
  id: string;
  /** Alias columns reference via their `model_alias` field. */
  alias: string;
  /** Model identifier / URN (e.g. `workspace/model-name`), from the model dropdown. */
  model: string;
  /** Model provider name (e.g. `openai`, or `workspace/provider-name`). */
  provider: string;
  /** Inference parameters (temperature, top_p, max_tokens, …), from the params popover. */
  inferenceParams: Partial<InferenceParams>;
}

/** The editable fields of a {@link BuilderModel} (everything but its id). */
export type BuilderModelPatch = Partial<Omit<BuilderModel, 'id'>>;

/**
 * Resolves the provider for a model URN from the platform model list: the model's first
 * `model_providers` entry (a `workspace/provider-name` resource ref). Data Designer needs
 * an explicit provider on each model config — an unset provider is deprecated and the job
 * fails with "the model does not have a provider". Returns '' when the model isn't found
 * or has no provider (the user can still fill it in manually).
 */
export const providerForModel = (modelGroups: ModelWorkspaceGroup[], model: string): string => {
  for (const group of modelGroups) {
    for (const entity of group.models) {
      if (getURNFromNamedEntityRef(entity) === model) return entity.model_providers?.[0] ?? '';
    }
  }
  return '';
};

/**
 * The first platform model (with its resolved provider) from the model list, used to
 * auto-fill a template's model so the recipe can be previewed without picking one by
 * hand. Returns null when no models are available.
 */
export const firstAvailableModel = (
  modelGroups: ModelWorkspaceGroup[]
): { model: string; provider: string } | null => {
  for (const group of modelGroups) {
    for (const entity of group.models) {
      const model = getURNFromNamedEntityRef(entity);
      if (model) return { model, provider: entity.model_providers?.[0] ?? '' };
    }
  }
  return null;
};

/**
 * Resolves the model + provider to auto-fill for a template-seeded model. Prefers a model
 * matching `preferred` (by full URN, or by name so it resolves across workspaces —
 * the URN's workspace prefix varies per user) when it exists in the workspace, otherwise
 * falls back to the first available model. Returns null when no models are available.
 */
export const resolveTemplateModel = (
  modelGroups: ModelWorkspaceGroup[],
  preferred?: string
): { model: string; provider: string } | null => {
  if (preferred) {
    for (const group of modelGroups) {
      for (const entity of group.models) {
        const urn = getURNFromNamedEntityRef(entity);
        const baseName = entity.name?.split('@')[0];
        if (urn && (urn === preferred || entity.name === preferred || baseName === preferred)) {
          return { model: urn, provider: entity.model_providers?.[0] ?? '' };
        }
      }
    }
  }
  return firstAvailableModel(modelGroups);
};

/**
 * Resolves a template's model specs into {@link BuilderModel}s, numbering ids from
 * `startId`. `model`/`provider` may be empty when the spec omits a preferred model — the
 * build route auto-fills them from the workspace once the platform model list loads.
 */
export const buildModelsFromTemplate = (
  specs: readonly TemplateModelSpec[] = [],
  startId = 0
): BuilderModel[] =>
  specs.map((spec, index) => ({
    id: `model-${startId + index}`,
    alias: spec.alias,
    model: spec.model ?? '',
    provider: '',
    inferenceParams: { ...spec.inferenceParams },
  }));

/**
 * A {@link BuilderModel} seeded from a platform model picked in the `ModelSelectV2`
 * dropdown, with a unique default alias the user can rename in the config panel. The
 * `provider` is resolved from the platform model list (see {@link providerForModel}) so
 * the submitted config carries it; inference parameters start empty and are refined in
 * the config panel.
 */
export const builderModelFromSelection = (
  id: string,
  selection: ModelSelection,
  provider: string,
  takenAliases: Set<string>
): BuilderModel => ({
  id,
  alias: defaultModelAlias(takenAliases),
  model: selection.model,
  provider,
  inferenceParams: {},
});

/** A default, unique model alias (e.g. `model_1`), never colliding with an existing one. */
export const defaultModelAlias = (takenAliases: Set<string>): string => {
  for (let n = 1; ; n++) {
    const candidate = `model_${n}`;
    if (!takenAliases.has(candidate)) return candidate;
  }
};

/** Validates a proposed model alias; returns an error message, or null if valid. */
export const validateModelAlias = (alias: string, takenAliases: Set<string>): string | null => {
  const trimmed = alias.trim();
  if (!trimmed) return 'Alias is required.';
  if (takenAliases.has(trimmed)) return 'A model with this alias already exists.';
  return null;
};

/**
 * Validates every model is ready to submit: unique, non-empty aliases and a chosen model.
 * Inference parameters are constrained by the `ModelSelectV2` params popover, so they are
 * not re-checked here. Returns one human-readable message per problem, or an empty array
 * if all models are valid.
 */
export const validateModels = (models: BuilderModel[]): string[] => {
  const errors: string[] = [];
  for (const model of models) {
    const label = model.alias.trim() || 'Model';
    const takenAliases = new Set(
      models.filter((other) => other.id !== model.id).map((other) => other.alias.trim())
    );
    const aliasError = validateModelAlias(model.alias, takenAliases);
    if (aliasError) errors.push(`${label}: ${aliasError}`);
    if (!model.model.trim()) errors.push(`${label}: A model must be selected.`);
  }
  return errors;
};

/** Converts one builder model into the SDK's model config shape. */
const toModelConfig = (model: BuilderModel): ModelConfig => {
  const config: ModelConfig = { alias: model.alias.trim(), model: model.model.trim() };
  if (model.provider.trim()) config.provider = model.provider.trim();

  const { temperature, top_p, max_tokens } = model.inferenceParams;
  const inference: ChatCompletionInferenceParams = {};
  if (temperature !== undefined) inference.temperature = temperature;
  if (top_p !== undefined) inference.top_p = top_p;
  if (max_tokens !== undefined) inference.max_tokens = max_tokens;
  if (Object.keys(inference).length > 0) {
    config.inference_parameters = { generation_type: 'chat-completion', ...inference };
  }
  return config;
};

/**
 * Builds the `model_configs` for the Data Designer job config. Call {@link validateModels}
 * first — this assumes the models are valid and does not re-check them. Returns undefined
 * when there are no models so the key is omitted from the config entirely.
 */
export const buildModelConfigs = (models: BuilderModel[]): ModelConfig[] | undefined =>
  models.length > 0 ? models.map(toModelConfig) : undefined;
