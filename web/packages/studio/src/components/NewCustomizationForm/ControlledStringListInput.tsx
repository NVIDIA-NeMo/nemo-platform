// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { UseControllerComponentProps } from '@nemo/common/src/types';
import { FormField, TextInput } from '@nvidia/foundations-react-core';
import { useController } from 'react-hook-form';

interface Props extends UseControllerComponentProps {
  placeholder?: string;
  disabled?: boolean;
}

/**
 * Edits a `string[]` field as one comma separated line — LoRA module lists and W&B tags
 * are both far easier to type that way than as repeated inputs.
 *
 * Blank yields `[]`, which the submit mapper turns into "send nothing" so the backend
 * keeps its own default rather than receiving an empty list as a filter.
 */
export const ControlledStringListInput = ({
  useControllerProps,
  formFieldProps,
  placeholder,
  disabled,
}: Props) => {
  const {
    field: { value, onChange, onBlur, disabled: fieldDisabled },
  } = useController(useControllerProps);

  return (
    <FormField {...formFieldProps}>
      <TextInput
        value={Array.isArray(value) ? (value as string[]).join(', ') : ''}
        placeholder={placeholder}
        disabled={disabled || fieldDisabled}
        onValueChange={(next: string) =>
          onChange(
            next
              .split(',')
              .map((part) => part.trim())
              .filter(Boolean)
          )
        }
        onBlur={onBlur}
      />
    </FormField>
  );
};
