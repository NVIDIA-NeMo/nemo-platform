// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { UseControllerComponentProps } from '@nemo/common/src/types';
import { FormField, TextArea } from '@nvidia/foundations-react-core';
import { useState } from 'react';
import { useController } from 'react-hook-form';

interface Props extends UseControllerComponentProps {
  label?: string;
  placeholder?: string;
  disabled?: boolean;
}

/**
 * Raw-JSON editor bound to a form field. Parses on change: valid JSON is written
 * to the field (as the parsed value — object, array, string, etc.), an empty box
 * clears it to `undefined`, and invalid JSON shows an inline error without
 * corrupting the stored value. Used for the customizer's free-form / nested
 * config fields (rope_scaling, loftq_config, layer_replication, …).
 */
export const ControlledJsonInput = ({
  useControllerProps,
  formFieldProps,
  label,
  placeholder,
  disabled,
}: Props) => {
  const {
    field: { value, onChange, onBlur, disabled: fieldDisabled },
  } = useController(useControllerProps);

  const [text, setText] = useState<string>(() =>
    value == null ? '' : JSON.stringify(value, null, 2)
  );
  const [parseError, setParseError] = useState<string>();

  const handleChange = (next: string) => {
    setText(next);
    const trimmed = next.trim();
    if (!trimmed) {
      setParseError(undefined);
      onChange(undefined);
      return;
    }
    try {
      onChange(JSON.parse(trimmed));
      setParseError(undefined);
    } catch {
      setParseError('Invalid JSON');
    }
  };

  return (
    <FormField
      slotLabel={label}
      slotError={parseError ?? ''}
      status={parseError ? 'error' : undefined}
      {...formFieldProps}
    >
      <TextArea
        value={text}
        onValueChange={handleChange}
        onBlur={onBlur}
        disabled={disabled || fieldDisabled}
        placeholder={placeholder}
      />
    </FormField>
  );
};
