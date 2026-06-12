// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelSelectV2 } from '@nemo/common/src/components/ModelSelectV2/ModelSelectV2';
import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import { groupModelsByWorkspace } from '@nemo/common/src/utils/models';
import type { InferenceParams } from '@nemo/sdk/generated/platform/schema';
import { FormField } from '@nvidia/foundations-react-core';
import { useJudgeModels } from '@studio/hooks/evaluation/useJudgeModels';
import { useSetFieldErrorOnApiError } from '@studio/hooks/evaluation/useSetFieldErrorOnApiError';
import { useMemo } from 'react';
import { type FieldValues, type Path, useController, useFormContext } from 'react-hook-form';

export interface JudgeModelSelectProps<TFieldValues extends FieldValues = FieldValues> {
  required?: boolean;
  placeholder?: string;
  slotLabel?: string;
  requiredMessage?: string;
  dropdownSide?: 'top' | 'bottom';
  formFieldName: Path<TFieldValues>;
  showParams?: boolean;
  inferenceParams?: Partial<InferenceParams>;
  onInferenceParamsChange?: (params: Partial<InferenceParams>) => void;
}

/**
 * Model selector specifically for judge models in LLM-as-a-Judge evaluation.
 * Fetches models from all workspaces, not just the current workspace.
 */
export const JudgeModelSelect = <TFieldValues extends FieldValues = FieldValues>({
  required = false,
  placeholder = 'Select a judge model',
  slotLabel = 'Judge Model',
  requiredMessage = 'Judge model is required',
  dropdownSide,
  formFieldName,
  showParams = false,
  inferenceParams,
  onInferenceParamsChange,
}: JudgeModelSelectProps<TFieldValues>) => {
  const {
    control,
    formState: { disabled, isSubmitting },
  } = useFormContext<TFieldValues>();

  const { field, fieldState } = useController({
    control,
    name: formFieldName,
    rules: required ? { required: requiredMessage } : undefined,
  });

  const { data: judgeModels, isLoading, error } = useJudgeModels({ enabled: !disabled });

  useSetFieldErrorOnApiError<TFieldValues>(formFieldName, error);

  const groups = useMemo(() => groupModelsByWorkspace(judgeModels ?? []), [judgeModels]);

  const value: ModelSelection | null = field.value ? { model: field.value as string } : null;

  const handleValueChange = (selection: ModelSelection) => {
    field.onChange(selection.model);
  };

  const handleOpenChange = (isOpen: boolean) => {
    if (!isOpen) field.onBlur();
  };

  return (
    <FormField slotLabel={slotLabel} slotError={fieldState.error?.message} required={required}>
      <ModelSelectV2
        value={value}
        onValueChange={handleValueChange}
        groups={groups}
        loading={isLoading}
        disabled={isSubmitting || disabled}
        placeholder={placeholder}
        showParams={showParams}
        inferenceParams={inferenceParams}
        onInferenceParamsChange={onInferenceParamsChange}
        onOpenChange={handleOpenChange}
        dropdownSide={dropdownSide}
        fullWidth
      />
    </FormField>
  );
};
