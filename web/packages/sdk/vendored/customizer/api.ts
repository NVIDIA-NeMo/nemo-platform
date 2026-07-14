// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// TEMP: customizer-specific React Query hooks inlined while the customizer SDK is being rebuilt.
// The customizer UI now READS jobs through the generic platform jobs API (useJobsGetJob) and only
// needs a per-backend cancel mutation here. Reads: `@nemo/sdk/generated/platform/api` (useJobsGetJob).
// Restore SDK imports once the customizer SDK regenerates with per-backend support.

import { useMutation } from '@tanstack/react-query';
import type {
  MutationFunction,
  QueryClient,
  UseMutationOptions,
  UseMutationResult,
} from '@tanstack/react-query';

import { customFetch } from '../../generated/fetchers/platform';
import type { ErrorType } from '../../generated/fetchers/platform';
import type { HTTPValidationError } from '../../generated/platform/schema';

import type {
  AutomodelJobInput,
  CustomizationBackend,
  CustomizationJob,
  UnslothJobInput,
} from './schema';

interface CustomizationCancelJobVariables {
  workspace: string;
  backend: CustomizationBackend;
  name: string;
}

/**
 * @summary Cancel a customization job on its backend collection.
 */
export const customizationCancelJob = (
  { workspace, backend, name }: CustomizationCancelJobVariables,
  signal?: AbortSignal
) => {
  return customFetch<CustomizationJob>({
    url: `/apis/customization/v2/workspaces/${encodeURIComponent(String(workspace))}/${encodeURIComponent(String(backend))}/jobs/${encodeURIComponent(String(name))}/cancel`,
    method: 'POST',
    signal,
  });
};

export const getCustomizationCancelJobMutationOptions = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof customizationCancelJob>>,
    TError,
    CustomizationCancelJobVariables,
    TContext
  >;
}): UseMutationOptions<
  Awaited<ReturnType<typeof customizationCancelJob>>,
  TError,
  CustomizationCancelJobVariables,
  TContext
> => {
  const mutationKey = ['customizationCancelJob'];
  const { mutation: mutationOptions } = options
    ? options.mutation && 'mutationKey' in options.mutation && options.mutation.mutationKey
      ? options
      : { ...options, mutation: { ...options.mutation, mutationKey } }
    : { mutation: { mutationKey } };

  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof customizationCancelJob>>,
    CustomizationCancelJobVariables
  > = (props) => customizationCancelJob(props);

  return { mutationFn, ...mutationOptions };
};

export type CustomizationCancelJobMutationResult = NonNullable<
  Awaited<ReturnType<typeof customizationCancelJob>>
>;

export type CustomizationCancelJobMutationError = ErrorType<HTTPValidationError>;

// ----- Create: automodel -----

interface CustomizationCreateAutomodelJobVariables {
  workspace: string;
  data: AutomodelJobInput;
}

export const customizationCreateAutomodelJob = (
  { workspace, data }: CustomizationCreateAutomodelJobVariables,
  signal?: AbortSignal
) => {
  return customFetch<CustomizationJob>({
    url: `/apis/customization/v2/workspaces/${encodeURIComponent(String(workspace))}/automodel/jobs`,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    data,
    signal,
  });
};

export const useCustomizationCreateAutomodelJob = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof customizationCreateAutomodelJob>>,
    TError,
    CustomizationCreateAutomodelJobVariables,
    TContext
  >;
}) => {
  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof customizationCreateAutomodelJob>>,
    CustomizationCreateAutomodelJobVariables
  > = (props) => customizationCreateAutomodelJob(props);
  return useMutation({ mutationFn, ...options?.mutation });
};

// ----- Create: unsloth -----

interface CustomizationCreateUnslothJobVariables {
  workspace: string;
  data: UnslothJobInput;
}

export const customizationCreateUnslothJob = (
  { workspace, data }: CustomizationCreateUnslothJobVariables,
  signal?: AbortSignal
) => {
  return customFetch<CustomizationJob>({
    url: `/apis/customization/v2/workspaces/${encodeURIComponent(String(workspace))}/unsloth/jobs`,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    data,
    signal,
  });
};

export const useCustomizationCreateUnslothJob = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(options?: {
  mutation?: UseMutationOptions<
    Awaited<ReturnType<typeof customizationCreateUnslothJob>>,
    TError,
    CustomizationCreateUnslothJobVariables,
    TContext
  >;
}) => {
  const mutationFn: MutationFunction<
    Awaited<ReturnType<typeof customizationCreateUnslothJob>>,
    CustomizationCreateUnslothJobVariables
  > = (props) => customizationCreateUnslothJob(props);
  return useMutation({ mutationFn, ...options?.mutation });
};

/**
 * @summary Cancel Job
 */
export const useCustomizationCancelJob = <
  TError = ErrorType<HTTPValidationError>,
  TContext = unknown,
>(
  options?: {
    mutation?: UseMutationOptions<
      Awaited<ReturnType<typeof customizationCancelJob>>,
      TError,
      CustomizationCancelJobVariables,
      TContext
    >;
  },
  queryClient?: QueryClient
): UseMutationResult<
  Awaited<ReturnType<typeof customizationCancelJob>>,
  TError,
  CustomizationCancelJobVariables,
  TContext
> => {
  return useMutation(getCustomizationCancelJobMutationOptions(options), queryClient);
};
