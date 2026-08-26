// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { UseControllerComponentProps } from '@nemo/common/src/types';
import { Button, Flex, FormField, TextInput } from '@nvidia/foundations-react-core';
import { type ReactNode, useRef } from 'react';
import { useController } from 'react-hook-form';

interface Props extends UseControllerComponentProps {
  /** Comma-joined extension list for the native picker, e.g. ``.yaml,.yml,.json``. */
  accept: string;
  label: string;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  slotHelp?: ReactNode;
}

/** A file field shaped like the rest of this form: the chosen filename sits in a read-only
 *  text input with an Upload button beside it, rather than a dropzone. Form state holds the
 *  `File` itself — the caller reads its text at submit, so nothing is uploaded on pick. */
export const EvalFilePickerField = ({
  useControllerProps,
  accept,
  label,
  placeholder,
  required,
  disabled,
  slotHelp,
  formFieldProps,
}: Props) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const {
    field: { onChange, value },
    fieldState: { error },
  } = useController(useControllerProps);
  const file = value as File | undefined;

  return (
    <FormField
      name={useControllerProps.name}
      slotLabel={label}
      slotHelp={slotHelp}
      slotError={error?.message?.toString()}
      status={error ? 'error' : undefined}
      required={required}
      {...formFieldProps}
    >
      <Flex gap="density-md" align="center" className="w-full">
        <TextInput
          value={file?.name ?? ''}
          placeholder={placeholder}
          readOnly
          disabled={disabled}
          status={error ? 'error' : undefined}
          aria-label={label}
          onChange={() => undefined}
        />
        <Button
          color="neutral"
          kind="secondary"
          disabled={disabled}
          onClick={(event) => {
            // The picker lives inside a form; without this the click submits it.
            event.preventDefault();
            inputRef.current?.click();
          }}
        >
          Upload
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(event) => {
            onChange(event.currentTarget.files?.[0]);
            // Clear the native value so re-picking the same file after a parse error still fires.
            event.currentTarget.value = '';
          }}
        />
      </Flex>
    </FormField>
  );
};
