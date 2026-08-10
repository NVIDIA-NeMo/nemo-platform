// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal, FormModalProps } from '@nemo/common/src/components/FormModal';
import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { NotifyFn } from '@nemo/common/src/providers/toast/types';
import { useNotify } from '@nemo/common/src/providers/toast/useNotify';
import { getErrorMessage } from '@nemo/common/src/utils/error';
import { handleFormErrorsGeneric } from '@nemo/common/src/utils/forms/error';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { type ComponentProps, type FC, useState } from 'react';
import { useForm } from 'react-hook-form';

interface FormFields {
  confirmText: string;
}

type SubmitButtonColor = NonNullable<ComponentProps<typeof LoadingButton>['color']>;

export interface ConfirmationModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  /** Return true when the action succeeded (shows success toast); false shows error toast. */
  onConfirm: () => boolean | Promise<boolean>;
  title: string;
  /** Body copy shown above the optional confirmation field. */
  description: string;
  /** When set with `simpleConfirm === false`, user must type this exact string to enable submit. */
  confirmationText?: string;
  /** If true (default), only a single button click is required. Set `false` to require typing `confirmationText`. */
  simpleConfirm?: boolean;
  successText?: string;
  errorText?: string;
  submitButtonText?: string;
  /** Passed to the submit button; omit for default (non-destructive) styling. */
  submitButtonColor?: SubmitButtonColor;
  /** When true, success and error toasts from this modal are skipped (caller handles feedback). */
  suppressResultToasts?: boolean;
  /** Where result messages go. Defaults to the surrounding ToastProvider; plugins pass `host.notifications.notify`. */
  onNotify?: NotifyFn;
}

export const ConfirmationModal: FC<ConfirmationModalProps> = ({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmationText,
  simpleConfirm = true,
  successText = 'Done.',
  errorText = 'Something went wrong. Please try again.',
  submitButtonText = 'Confirm',
  submitButtonColor,
  suppressResultToasts = false,
  onNotify,
}) => {
  const {
    reset,
    control,
    handleSubmit,
    formState: { isValid },
  } = useForm<FormFields>({
    mode: 'onChange',
    defaultValues: { confirmText: '' },
  });
  const [isPending, setIsPending] = useState(false);
  const notify = useNotify(onNotify);

  const resetAndClose = () => {
    reset();
    onClose();
  };

  const onSubmit = async () => {
    setIsPending(true);
    try {
      const ok = await onConfirm();
      if (!suppressResultToasts) {
        if (ok) {
          notify(successText, 'success');
        } else {
          notify(errorText, 'error');
        }
      }
    } catch (error: unknown) {
      notify(getErrorMessage(error), 'error');
    } finally {
      resetAndClose();
      setIsPending(false);
    }
  };

  const confirmationMessage = confirmationText ? `Type "${confirmationText}" to confirm` : '';

  const validateConfirmationText = (confirmationTextInput: string) =>
    confirmationTextInput === confirmationText || confirmationMessage;

  return (
    <FormModal
      open={open}
      title={title}
      submitButtonText={submitButtonText}
      disabled={isPending}
      submitDisabled={simpleConfirm ? false : !isValid}
      loading={isPending}
      onSubmit={handleSubmit(
        onSubmit,
        handleFormErrorsGeneric({ title: 'Confirmation Form Errors' })
      )}
      onClose={resetAndClose}
      attributes={
        submitButtonColor
          ? {
              SubmitButton: {
                color: submitButtonColor,
              },
            }
          : undefined
      }
    >
      <Stack gap="density-md">
        <Text className={`leading-relaxed ${simpleConfirm ? 'mb-4' : ''}`}>{description}</Text>
        {!simpleConfirm && (
          <ControlledTextInput
            useControllerProps={{
              control,
              name: 'confirmText',
              rules: {
                required: confirmationMessage,
                validate: (confirmationTextInput) =>
                  validateConfirmationText(confirmationTextInput),
              },
            }}
            label="Confirmation"
            required
            placeholder={confirmationMessage}
            autoFocus
          />
        )}
      </Stack>
    </FormModal>
  );
};
