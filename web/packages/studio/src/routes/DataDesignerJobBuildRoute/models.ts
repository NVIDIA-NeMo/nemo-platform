// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withOperators } from '@nemo/common/src/api/filterOperators';
import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import { MAX_COMPLETION_TOKENS_DEFAULT } from '@nemo/common/src/constants/inferenceParameters';
import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import { groupModelsByWorkspace } from '@nemo/common/src/utils/models';
import type {
  ChatCompletionInferenceParams,
  EmbeddingInferenceParams,
  EmbeddingInferenceParamsExtraBody,
  ModelConfig,
} from '@nemo/sdk/generated/data-designer/schema';
import { modelsListModels } from '@nemo/sdk/generated/platform/api';
import type {
  InferenceParams,
  ModelEntity,
  ModelEntityFilter,
  ModelProvider,
} from '@nemo/sdk/generated/platform/schema';
import type { TemplateModelSpec } from '@studio/components/CreateFilesetStart/types';

/** Mirrors the SDK ModelConfig shape; `alias` is what LLM columns reference via `model_alias`. */
export interface BuilderModel {
  /** Canvas-unique id (stable across alias edits, used for selection). */
  id: string;
  alias: string;
  model: string;
  provider: string;
  inferenceParams: Partial<InferenceParams>;
}

export type BuilderModelPatch = Partial<Omit<BuilderModel, 'id'>>;

/**
 * The provider a dropdown selection carries: the picked model's first `model_providers` entry
 * (a `workspace/provider-name` resource ref). Data Designer needs an explicit provider on each
 * model config — an unset provider is deprecated and the job fails with "the model does not have
 * a provider". Returns '' when the entry has no provider, or when the selection arrived without
 * its entity (the user can still fill it in manually).
 */
export const providerForSelection = (selection: ModelSelection): string =>
  selection.entity?.model_providers?.[0] ?? '';

/** One page is plenty: auto-fill only ever needs a name match or a first choice. */
const AUTO_FILL_PAGE_SIZE = 25;

/**
 * The models {@link resolveTemplateModel} should consider: those whose name matches `preferred`,
 * plus the first page of the workspace as a fallback. Two small requests instead of walking the
 * whole catalogue, which is all the resolver needs to make its choice.
 */
export const fetchAutoFillCandidates = async (
  workspace: string,
  preferred?: string
): Promise<ModelWorkspaceGroup[]> => {
  const listPage = async (filter?: ModelEntityFilter): Promise<ModelEntity[]> => {
    const page = await modelsListModels(workspace, {
      page_size: AUTO_FILL_PAGE_SIZE,
      sort: 'name',
      ...(filter ? { filter } : {}),
    });
    return page.data ?? [];
  };

  // Template specs name a model without its workspace prefix or version suffix; match on that.
  const preferredName = preferred
    ? (preferred.split('/').pop() ?? preferred).split('@')[0]
    : undefined;

  const [matches, firstPage] = await Promise.all([
    preferredName
      ? listPage(withOperators<ModelEntityFilter>({ name: { $like: preferredName } }))
      : Promise.resolve<ModelEntity[]>([]),
    listPage(),
  ]);

  const seen = new Set<string>();
  const models = [...matches, ...firstPage].filter((entity) => {
    const urn = getURNFromNamedEntityRef(entity);
    if (!urn || seen.has(urn)) return false;
    seen.add(urn);
    return true;
  });

  return groupModelsByWorkspace(models);
};

export const buildServedModelNames = (providers: ModelProvider[]): Map<string, string> => {
  const servedModelNames = new Map<string, string>();
  for (const provider of providers) {
    for (const served of provider.served_models ?? []) {
      if (served.model_entity_id && !servedModelNames.has(served.model_entity_id)) {
        servedModelNames.set(served.model_entity_id, served.served_model_name);
      }
    }
  }
  return servedModelNames;
};

export const modelIdForModel = (servedModelNames: Map<string, string>, model: string): string =>
  servedModelNames.get(model) || model;

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

export const validateModelAlias = (alias: string, takenAliases: Set<string>): string | null => {
  const trimmed = alias.trim();
  if (!trimmed) return 'Alias is required.';
  if (takenAliases.has(trimmed)) return 'A model with this alias already exists.';
  return null;
};

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

/**
 * Maps a builder model's params to the SDK's discriminated inference-parameter union. A
 * `generation_type: 'embedding'` marker (set by embedding-model templates) routes to
 * {@link EmbeddingInferenceParams} so embedding-only fields — notably `extra_body`, which
 * carries the `input_type` that NVIDIA retrieval-QA embedders require — reach the request.
 * Everything else defaults to chat-completion.
 */
const toInferenceParameters = (
  params: Partial<InferenceParams>
): ChatCompletionInferenceParams | EmbeddingInferenceParams => {
  if (params.generation_type === 'embedding') {
    const inference: EmbeddingInferenceParams = { generation_type: 'embedding' };
    const { encoding_format, extra_body, dimensions } = params;
    if (encoding_format === 'float' || encoding_format === 'base64') {
      inference.encoding_format = encoding_format;
    }
    if (extra_body && typeof extra_body === 'object') {
      inference.extra_body = extra_body as EmbeddingInferenceParamsExtraBody;
    }
    if (typeof dimensions === 'number') inference.dimensions = dimensions;
    return inference;
  }

  const { temperature, top_p, max_tokens } = params;
  const inference: ChatCompletionInferenceParams = {
    generation_type: 'chat-completion',
    max_tokens: max_tokens ?? MAX_COMPLETION_TOKENS_DEFAULT,
  };
  if (temperature !== undefined) inference.temperature = temperature;
  if (top_p !== undefined) inference.top_p = top_p;
  return inference;
};

const toModelConfig = (model: BuilderModel, servedModelNames: Map<string, string>): ModelConfig => {
  const config: ModelConfig = {
    alias: model.alias.trim(),
    model: modelIdForModel(servedModelNames, model.model.trim()),
    provider: model.provider.trim(),
  };
  if (model.provider.trim()) config.provider = model.provider.trim();
  config.inference_parameters = toInferenceParameters(model.inferenceParams);
  return config;
};

/** Returns undefined when there are no models so the key is omitted from the config. */
export const buildModelConfigs = (
  models: BuilderModel[],
  servedModelNames: Map<string, string> = new Map()
): ModelConfig[] | undefined =>
  models.length > 0 ? models.map((model) => toModelConfig(model, servedModelNames)) : undefined;

/**
 * Inverse of {@link toInferenceParameters}: maps an SDK inference-parameter object back into
 * the loose {@link InferenceParams} shape the builder edits, keeping the `generation_type`
 * marker so embedding models round-trip through {@link toInferenceParameters} unchanged.
 */
const inferenceParamsFromConfig = (
  params: ModelConfig['inference_parameters']
): Partial<InferenceParams> => {
  if (!params) return {};
  if (params.generation_type === 'embedding') {
    const inference: Partial<InferenceParams> = { generation_type: 'embedding' };
    if (params.encoding_format) inference.encoding_format = params.encoding_format;
    if (params.extra_body) inference.extra_body = params.extra_body;
    if (typeof params.dimensions === 'number') inference.dimensions = params.dimensions;
    return inference;
  }

  const chat = params as ChatCompletionInferenceParams;
  const inference: Partial<InferenceParams> = { generation_type: 'chat-completion' };
  if (typeof chat.temperature === 'number') inference.temperature = chat.temperature;
  if (typeof chat.top_p === 'number') inference.top_p = chat.top_p;
  if (typeof chat.max_tokens === 'number') inference.max_tokens = chat.max_tokens;
  return inference;
};

/**
 * Reverses {@link buildModelConfigs} into builder models so an existing job's `model_configs`
 * can pre-fill the build canvas (used when cloning a job). The stored `model` is the served
 * model name; it is preserved verbatim so the cloned job submits the same config.
 */
export const buildModelsFromConfig = (configs: ModelConfig[] = [], startId = 0): BuilderModel[] =>
  configs.map((config, index) => ({
    id: `model-${startId + index}`,
    alias: config.alias,
    model: config.model,
    provider: config.provider ?? '',
    inferenceParams: inferenceParamsFromConfig(config.inference_parameters),
  }));
