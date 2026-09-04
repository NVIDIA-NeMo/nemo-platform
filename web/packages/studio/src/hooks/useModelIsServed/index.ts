// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import {
  getModelsGetProviderQueryKey,
  modelsGetProvider,
} from '@nemo/sdk/generated/platform/model-providers';
import type { ModelEntity, ModelProvider } from '@nemo/sdk/generated/platform/schema';
import { useQueries } from '@tanstack/react-query';
import { useMemo } from 'react';

interface UseModelIsServedResult {
  /** Whether at least one provider lists this model in its served_models. */
  isServed: boolean;
  isLoading: boolean;
}

function providerServesModel(provider: ModelProvider, modelEntityId: string): boolean {
  return (provider.served_models ?? []).some((sm) => sm.model_entity_id === modelEntityId);
}

export function useModelIsServed(model: ModelEntity | null | undefined): UseModelIsServedResult {
  const modelEntityId = model ? `${model.workspace}/${model.name}` : '';
  const providerRefs = model?.model_providers ?? [];
  const enabled = Boolean(model) && providerRefs.length > 0;

  const queries = useQueries({
    queries: providerRefs.map((ref) => {
      const parts = getPartsFromReference(ref);
      return {
        queryKey: getModelsGetProviderQueryKey(parts.workspace, parts.name),
        queryFn: () => modelsGetProvider(parts.workspace, parts.name),
        enabled,
        retry: false,
        staleTime: 5 * 60 * 1000,
      };
    }),
  });

  return useMemo(() => {
    if (!enabled) {
      return { isServed: false, isLoading: false };
    }

    const isLoading = queries.some((q) => q.isLoading);
    const isServed = queries.some((q) => q.data && providerServesModel(q.data, modelEntityId));

    return { isServed, isLoading };
  }, [enabled, queries, modelEntityId]);
}
