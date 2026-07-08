// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useJobsGetJob } from '@nemo/sdk/generated/platform/api';
import type { PlatformJobResponse } from '@nemo/sdk/generated/platform/schema';
import {
  getCustomizationBackend,
  type CustomizationBackend,
  type CustomizationJob,
  type CustomizationJobSpec,
} from '@nemo/sdk/vendored/customizer/schema';
import type { UseQueryOptions } from '@tanstack/react-query';

/**
 * Query options accepted by {@link useCustomizationJob}. Customization jobs are read through the
 * generic platform jobs API, which is keyed by name only; the training backend is derived from the
 * returned spec shape (automodel specs carry `parallelism`, unsloth specs carry `hardware`).
 */
export type CustomizationJobQueryOptions = Partial<
  UseQueryOptions<PlatformJobResponse, unknown, PlatformJobResponse>
>;

export interface UseCustomizationJobResult {
  /** The job with its spec narrowed to the per-backend union, or `undefined` while loading/on error. */
  job?: CustomizationJob;
  /** The training backend derived from the job spec, or `undefined` if it isn't a customization job. */
  backend?: CustomizationBackend;
  isLoading: boolean;
  isError: boolean;
  refetch: () => void;
}

/**
 * Fetch a customization job by name via the generic platform jobs API and narrow it to the typed
 * per-backend {@link CustomizationJob}. Because it uses the shared `useJobsGetJob` query key, multiple
 * consumers on the same job de-duplicate to a single request.
 */
export const useCustomizationJob = (
  workspace: string,
  name: string,
  query?: CustomizationJobQueryOptions
): UseCustomizationJobResult => {
  const { data, isLoading, isError, refetch } = useJobsGetJob<PlatformJobResponse, unknown>(
    workspace,
    name,
    { query: query ?? {} }
  );

  const backend = getCustomizationBackend(data?.spec);
  const job =
    data && backend
      ? ({ ...data, spec: data.spec as unknown as CustomizationJobSpec } as CustomizationJob)
      : undefined;

  return {
    job,
    backend,
    isLoading,
    isError,
    refetch: () => {
      void refetch();
    },
  };
};
