// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  type Adapter,
  ModelDeploymentStatus,
  type ModelEntity,
} from '@nemo/sdk/generated/platform/schema';

import { buildWorkspaceGroup, type ModelWorkspaceGroup } from '../api/models/useModels';
import { getURNFromNamedEntityRef } from '../namedEntity';
import type { ResourceRef } from '../types';

const DEFAULT_WORKSPACE = 'default';

/**
 * Groups a flat list of models into {@link ModelWorkspaceGroup}s keyed by
 * `model.workspace` (falling back to `'default'`). Empty input yields `[]`.
 *
 * Pass `sort: true` to sort the resulting groups alphabetically by workspace
 * name. Models within each group preserve their input order.
 */
export const groupModelsByWorkspace = (
  models: ModelEntity[],
  { sort = false }: { sort?: boolean } = {}
): ModelWorkspaceGroup[] => {
  if (!models.length) return [];
  const byWorkspace = models.reduce<Record<string, ModelEntity[]>>((acc, model) => {
    const ws = model.workspace ?? DEFAULT_WORKSPACE;
    (acc[ws] ??= []).push(model);
    return acc;
  }, {});
  const entries = Object.entries(byWorkspace);
  if (sort) entries.sort(([a], [b]) => a.localeCompare(b));
  return entries.map(([ws, ms]) => buildWorkspaceGroup(ws, ms));
};

export const hasModelProvider = (model: ModelEntity): boolean =>
  Array.isArray(model.model_providers) && model.model_providers.length > 0;

/**
 * Returns true if the model is a base model, false otherwise. This is determined by
 * checking if the model has a base_model property.
 *
 * @param model - The model to check.
 * @returns True if the model is a base model, false otherwise.
 */
export const isBaseModel = (model: ModelEntity) => {
  return model.base_model === undefined;
};

/**
 * Given a ModelEntity, return the base model URN
 * @param model - The model to get the base model for
 * @returns The base model URN
 */
export const getBaseModelURN = (model: ModelEntity) => {
  if (typeof model.base_model === 'string') {
    return model.base_model;
  }
  return getURNFromNamedEntityRef(model.base_model);
};

/**
 * Build a model config for evaluation related types like targets and metrics
 * @param model_id - The model URN to build the config for
 * @returns The model config
 */
export const buildModelConfig = (
  model_id: ResourceRef,
  platformUrl: string,
  isChat: boolean = true
) => {
  return {
    api_endpoint: {
      url: isChat ? `${platformUrl}/v1/chat/completions` : `${platformUrl}/v1/completions`,
      model_id,
      format: 'nim' as const,
    },
  };
};

export const MODEL_DEPLOYMENT_GRACE_PERIOD_MS = 5 * 60 * 1000; // 5 minutes

// Matches timezone indicators: Z, +HH:MM, -HH:MM, +HHMM, -HHMM
const TIMEZONE_REGEX = /(Z|[+-]\d{2}:?\d{2})$/;

/**
 * Check if a model was created within the deployment grace period.
 * Models need time after creation for the backend to deploy them and populate the artifact.
 */
const isWithinDeploymentGracePeriod = (model: ModelEntity) => {
  if (!model.created_at) {
    return false;
  }
  // Ensure the timestamp is parsed as UTC if no timezone indicator is present
  const hasTimezone = TIMEZONE_REGEX.test(model.created_at);
  const timestamp = hasTimezone ? model.created_at : `${model.created_at}Z`;
  const createdAt = new Date(timestamp).getTime();
  const now = Date.now();
  return now - createdAt < MODEL_DEPLOYMENT_GRACE_PERIOD_MS;
};

export type ModelChatStatus = 'enabled' | 'disabled' | 'pending';

const DEPLOYMENT_TERMINAL_DISABLED: ReadonlySet<ModelDeploymentStatus> = new Set([
  ModelDeploymentStatus.ERROR,
  ModelDeploymentStatus.DELETED,
  ModelDeploymentStatus.LOST,
  ModelDeploymentStatus.DELETING,
]);

export type GetModelEntityChatStatusOptions = {
  /**
   * When the UI is scoped to an adapter row, chat requires a READY deployment
   * (same as entities with `base_model`).
   */
  adapter?: Adapter | null;
  /** Provider/deployment chain is still loading */
  deploymentLoading?: boolean;
  /**
   * Resolved {@link ModelDeploymentStatus} for the entity that backs inference
   * (e.g. base model when `model.base_model` is set — callers resolve which entity to query).
   * - Omit when no deployment query ran (list/playground): legacy optimistic behavior.
   * - `null` when no deployment exists.
   */
  deploymentStatus?: ModelDeploymentStatus | null;
};

/**
 * Whether chat can run for this model in the current UI context.
 *
 * Order of evaluation:
 * 1. `deploymentLoading` → `'pending'`
 * 2. Creation grace period → `'pending'`
 * 3. Entities with `base_model` or an **adapter** row need a READY deployment; `api_endpoint` alone is not enough.
 * 4. Standalone entities: `api_endpoint.url`, READY deployment, or (if deployment unknown) optimistic `'enabled'`.
 */
export function getModelEntityChatStatus(
  model: ModelEntity,
  options?: GetModelEntityChatStatusOptions
): ModelChatStatus {
  const { adapter, deploymentLoading, deploymentStatus } = options ?? {};

  if (deploymentLoading || isWithinDeploymentGracePeriod(model)) {
    return 'pending';
  }

  const hasApiEndpoint = Boolean(model.api_endpoint?.url);
  const needsReadyDeployment = Boolean(adapter) || Boolean(model.base_model);

  if (needsReadyDeployment) {
    if (deploymentStatus === undefined || deploymentStatus === ModelDeploymentStatus.READY) {
      return 'enabled';
    }
    if (deploymentStatus === null || DEPLOYMENT_TERMINAL_DISABLED.has(deploymentStatus)) {
      return 'disabled';
    }
    return 'pending';
  }

  if (
    hasApiEndpoint ||
    deploymentStatus === undefined ||
    deploymentStatus === ModelDeploymentStatus.READY
  ) {
    return 'enabled';
  }
  if (deploymentStatus === null || DEPLOYMENT_TERMINAL_DISABLED.has(deploymentStatus)) {
    return 'disabled';
  }
  return 'pending';
}

/**
 * Returns a boolean based on a search string and model. Checks if the model name, namespace, or URN matches the search string.
 * Returns true if the model matches the search string, false otherwise.
 */
export const filterModel = (model: ModelEntity, search?: string) => {
  const workspace = model.workspace;
  return !(
    search &&
    !model.name?.toLowerCase().includes(search.toLowerCase()) &&
    !workspace?.toLowerCase().includes(search.toLowerCase()) &&
    !getURNFromNamedEntityRef(model)?.toLowerCase().includes(search.toLowerCase())
  );
};
