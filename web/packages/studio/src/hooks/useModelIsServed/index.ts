// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { useServedModel } from '@studio/hooks/useServedModel';

interface UseModelIsServedResult {
  /** Whether at least one provider lists this model in its served_models. */
  isServed: boolean;
  isLoading: boolean;
}

export function useModelIsServed(model: ModelEntity | null | undefined): UseModelIsServedResult {
  const modelEntityId = model ? `${model.workspace}/${model.name}` : '';
  const { servedModel, isLoading } = useServedModel(model, modelEntityId);

  return { isServed: Boolean(servedModel), isLoading };
}
