// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TextInput, type TextInputProps } from '@nvidia/foundations-react-core';
import { useEffect, useRef, useState, type ChangeEvent, type JSX } from 'react';

export interface DebouncedTextInputProps extends TextInputProps {
  /**
   * The number of milliseconds to debounce the onValueChange handler.
   * @defaultValue 500
   */
  debounce?: number;
}

/** A TextInput component with a debounced onValueChange handler. */
export function DebouncedTextInput({
  debounce = 500,
  onValueChange,
  value: initialValue = '',
  ...props
}: DebouncedTextInputProps): JSX.Element {
  const [value, setValue] = useState(initialValue ?? '');
  const lastEventRef = useRef<ChangeEvent<HTMLInputElement> | null>(null);

  useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  useEffect(() => {
    const timeout = setTimeout(() => {
      if (lastEventRef.current) {
        onValueChange?.(value, lastEventRef.current);
      }
    }, debounce);
    return () => clearTimeout(timeout);
  }, [debounce, onValueChange, value]);

  return (
    <TextInput
      {...props}
      value={value}
      onValueChange={(next, event) => {
        lastEventRef.current = event;
        setValue(next);
      }}
    />
  );
}
