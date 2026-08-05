// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useEffect } from 'react';
import { FieldValues, Path, PathValue, useFormContext } from 'react-hook-form';
import { useSearchParams } from 'react-router';

export interface UseAutofillFromSearchParamsProps<TFieldValues extends FieldValues> {
  searchParamName: string;
  fieldName: Path<TFieldValues>;
  enabled?: boolean;
}

/**
 * Hook to autofill a form field from a search param
 * @param searchParamName - The name of the search param to autofill from
 * @param fieldName - The name of the field to autofill
 * @param enabled - Whether to enable autofill (defaults to true)
 */
export const useAutofillFromSearchParams = <TFieldValues extends FieldValues>({
  searchParamName,
  fieldName,
  enabled = true,
}: UseAutofillFromSearchParamsProps<TFieldValues>) => {
  const { setValue } = useFormContext<TFieldValues>();

  const [searchParams] = useSearchParams();
  const searchParamValue = searchParams.get(searchParamName);

  useEffect(() => {
    if (enabled && searchParamValue) {
      setValue(
        fieldName,
        decodeURIComponent(searchParamValue) as PathValue<TFieldValues, Path<TFieldValues>>
      );
    }
  }, [enabled, fieldName, searchParamValue, setValue]);
};
