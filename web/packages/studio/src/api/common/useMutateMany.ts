// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  useMutation,
  type UseMutationOptions,
  type UseMutationResult,
} from '@tanstack/react-query';

export interface UseMutateManyOptions<TData, TVariables> extends Omit<
  UseMutationOptions<TData[], Error, TVariables[]>,
  'mutationFn'
> {
  /** Verb used in the error message, e.g. "delete". Defaults to "create". */
  action?: string;
}

export const useMutateMany = <TData, TVariables>(
  mutationFn: (variables: TVariables) => Promise<TData>,
  options?: UseMutateManyOptions<TData, TVariables>
): UseMutationResult<TData[], Error, TVariables[]> => {
  const { action = 'create', ...mutationOptions } = options ?? {};

  return useMutation({
    ...mutationOptions,
    mutationFn: async (items: TVariables[]) => {
      const results = await Promise.allSettled(items.map((item) => mutationFn(item)));

      const failedItems = results.filter(
        (result): result is PromiseRejectedResult => result.status === 'rejected'
      );

      if (failedItems.length > 0) {
        throw new Error(
          `Failed to ${action} ${failedItems.length} out of ${items.length} items. Errors: ${failedItems.map((failure) => (failure.reason instanceof Error ? failure.reason.message : String(failure.reason))).join('; ')}`
        );
      }

      return results
        .filter((result) => result.status === 'fulfilled')
        .map((result) => result.value);
    },
  });
};
