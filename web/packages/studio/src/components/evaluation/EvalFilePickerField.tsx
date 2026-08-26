// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { UseControllerComponentProps } from '@nemo/common/src/types';
import {
  FormField,
  UploadContent,
  UploadDescription,
  UploadInputElement,
  UploadRoot,
  UploadTrigger,
} from '@nvidia/foundations-react-core';
import { type ReactNode } from 'react';
import { useController } from 'react-hook-form';

interface Props extends UseControllerComponentProps {
  /** Comma-joined extension list for the picker, e.g. ``.yaml,.yml,.json``. */
  accept: string;
  label: string;
  /** Helper text rendered inside the dropzone, naming what it takes. */
  hint: ReactNode;
  required?: boolean;
  disabled?: boolean;
  slotHelp?: ReactNode;
  /**
   * Error owned by the caller — a parse failure or an unsupported config shape, neither of
   * which is knowable until the file has been read. Takes precedence over the field's own
   * validation message so one field only ever shows one error.
   */
  slotError?: string;
}

/** A single-file drag-and-drop field bound to react-hook-form.
 *
 *  Form state holds the `File` itself rather than an upload record: nothing is sent when a file
 *  is picked, and the caller reads its text at submit.
 *
 *  The composed `Upload` parts are used rather than the `Upload` convenience component because
 *  it renders the file list *after* the trigger, which would leave a picked file sitting below
 *  its own error message. Composing puts exactly one of the two inside the `FormField` — the
 *  dropzone, or the file that replaced it — so the error always reads as belonging to the file
 *  above it, and a second file cannot be added without removing the first. */
export const EvalFilePickerField = ({
  useControllerProps,
  accept,
  label,
  hint,
  required,
  disabled,
  slotHelp,
  slotError,
  formFieldProps,
}: Props) => {
  const {
    field: { onChange, value },
    fieldState: { error },
  } = useController(useControllerProps);

  const file = value as File | undefined;
  const errorText = slotError ?? error?.message?.toString();

  return (
    <UploadRoot
      multiple={false}
      disabled={disabled}
      value={file ? { id: file.name, file, status: 'success' } : undefined}
      onValueChange={(item) => onChange(item?.file)}
      onFileRemove={() => onChange(undefined)}
    >
      <FormField
        name={useControllerProps.name}
        required={required}
        slotLabel={label}
        slotHelp={slotHelp}
        slotError={errorText}
        status={errorText ? 'error' : undefined}
        {...formFieldProps}
      >
        {file ? (
          <UploadContent />
        ) : (
          <UploadTrigger status={errorText ? 'error' : undefined}>
            <UploadInputElement accept={accept} aria-label={label} />
            <UploadDescription>{hint}</UploadDescription>
          </UploadTrigger>
        )}
      </FormField>
    </UploadRoot>
  );
};
