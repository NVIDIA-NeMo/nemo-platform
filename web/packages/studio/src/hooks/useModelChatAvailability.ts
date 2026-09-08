// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useModelsGetModel } from '@nemo/sdk/generated/platform/models';
import type { Adapter, ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { useModelDeploymentStatus } from '@studio/hooks/useModelDeploymentStatus';
import { useModelEntityChatStatusWithGrace } from '@studio/hooks/useModelEntityChatStatusWithGrace';
import { useModelIsServed } from '@studio/hooks/useModelIsServed';

interface UseModelChatAvailabilityOptions {
  adapter?: Adapter | null;
}

export function useModelChatAvailability(
  model: ModelEntity | null | undefined,
  options?: UseModelChatAvailabilityOptions
) {
  const adapter = options?.adapter;
  // For models with a base_model (customized/prompt-tuned), deployment lives
  // on the base model. For adapters, check the model itself directly.
  const baseModelName = adapter ? undefined : model?.base_model;

  const { data: baseModelEntity, isLoading: isLoadingBaseModel } = useModelsGetModel(
    model?.workspace ?? '',
    baseModelName ?? '',
    undefined,
    { query: { enabled: Boolean(baseModelName), retry: false } }
  );

  const modelForStatus = baseModelName ? baseModelEntity : model;
  const { status: deploymentStatus, isLoading: isStatusLoading } = useModelDeploymentStatus(
    modelForStatus ?? undefined
  );
  const { isServed, isLoading: isServedLoading } = useModelIsServed(modelForStatus);

  const isLoading = baseModelName
    ? isLoadingBaseModel || isStatusLoading || isServedLoading
    : isStatusLoading || isServedLoading;

  // Use the original model entity for grace period / api_endpoint checks;
  // deployment status comes from the resolved model (base or self).
  const graceStatus = useModelEntityChatStatusWithGrace(model, {
    adapter,
    deploymentStatus,
    deploymentLoading: isLoading,
  });

  // If the grace/deployment check says enabled but no provider actually serves
  // the model, override to disabled. This catches stale model_providers refs
  // where the model was removed from the provider's served_models.
  const modelChatStatus =
    graceStatus === 'enabled' && !isServedLoading && !isServed ? 'disabled' : graceStatus;

  const isChatAvailable = modelChatStatus === 'enabled';

  return { modelChatStatus, isChatAvailable, isLoading };
}
