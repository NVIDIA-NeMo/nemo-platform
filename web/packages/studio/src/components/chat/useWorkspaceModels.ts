// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { modelsListModels, getModelsListModelsQueryKey } from '@nemo/sdk/generated/platform/api';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { useQuery } from '@tanstack/react-query';

interface UseWorkspaceModelsResult {
  models: ModelEntity[];
  isLoading: boolean;
}

/**
 * Thin replacement for `useBaseModels` that doesn't try to merge in the
 * default-namespace models or sort/dedupe — keeps the Playground decoupled
 * from a pre-existing bug in `useBaseModels` where its post-fetch `.map` on
 * an undefined page entry throws during render. Returns the raw, filtered
 * `ModelEntity[]` for the requested workspace.
 */
export function useWorkspaceModels(workspace: string): UseWorkspaceModelsResult {
  const params = { page_size: 100, sort: 'name' as const };
  const query = useQuery({
    queryKey: getModelsListModelsQueryKey(workspace, params),
    queryFn: () => modelsListModels(workspace, params),
    enabled: !!workspace,
  });

  const raw = query.data?.data ?? [];
  const models = raw.filter((m): m is ModelEntity => !!m && typeof m.name === 'string');

  return { models, isLoading: query.isLoading };
}
