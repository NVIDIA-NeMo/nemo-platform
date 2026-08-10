/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledTextArea } from '@nemo/common/src/components/form/ControlledTextArea';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal, FormModalProps } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { ENTITY_NAME_HELP, entityNameSchema } from '@nemo/common/src/utils/entityName';
import {
  getSecretsListSecretsQueryKey,
  useSecretsCreateSecret,
} from '@nemo/sdk/generated/platform/api';
import { Stack } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { useQueryClient } from '@tanstack/react-query';
import { FC } from 'react';
import { SubmitHandler, useForm } from 'react-hook-form';
import { z } from 'zod';

const secretFormSchema = z.object({
  name: entityNameSchema('Name'),
  description: z.string().optional(),
  value: z.string().min(1, 'Secret value is required'),
});

type SecretFormData = z.infer<typeof secretFormSchema>;

const defaultValues: SecretFormData = {
  name: '',
  description: '',
  value: '',
};

interface CreateSecretModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
  /** Optional. After create, called with the new secret name (e.g. create-dataset flow sets the Secret Key field). */
  onSecretCreated?: (secretName: string) => void;
}

export const CreateSecretModal: FC<CreateSecretModalProps> = ({
  workspace,
  open,
  onClose,
  onSecretCreated,
}) => {
  const toast = useToast();
  const queryClient = useQueryClient();

  const {
    mutateAsync: createSecret,
    error: createError,
    isPending,
    reset: resetCreateMutation,
  } = useSecretsCreateSecret({
    mutation: {
      onSuccess: (data) => {
        onSecretCreated?.(data.name);
        toast.success('Secret created successfully');
        queryClient.invalidateQueries({ queryKey: getSecretsListSecretsQueryKey(workspace) });
        resetAndClose();
      },
    },
  });

  const {
    control,
    reset: resetForm,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(secretFormSchema),
    defaultValues,
    disabled: isPending,
    mode: 'onChange',
  });

  const reset = () => {
    resetCreateMutation();
    resetForm(defaultValues);
  };

  const resetAndClose = () => {
    reset();
    onClose();
  };

  const onSubmit: SubmitHandler<SecretFormData> = async (formData) => {
    try {
      await createSecret({
        workspace,
        data: {
          name: formData.name,
          description: formData.description,
          value: formData.value,
        },
      });
    } catch {
      // Error handling is done via toast in mutation onError
    }
  };

  return (
    <FormModal
      open={open}
      onClose={resetAndClose}
      title="Create Secret"
      instruction="To create a new secret, provide a name, description, and value. "
      submitButtonText="Create"
      onSubmit={handleSubmit(onSubmit)}
      disabled={isPending}
      loading={isPending}
      errorText={createError ? getErrorMessage(createError) : undefined}
    >
      <Stack gap="density-xl">
        <ControlledTextInput
          useControllerProps={{ control, name: 'name' }}
          name="name"
          label="Name"
          formFieldProps={{
            slotInfo:
              'Best practice: Use lowercase letters, numbers, and hyphens only to ensure compatibility with Kubernetes naming conventions.',
            slotHelp: ENTITY_NAME_HELP,
            slotError: errors.name?.message,
          }}
        />
        <ControlledTextArea
          useControllerProps={{ control, name: 'description' }}
          name="description"
          label="Description (optional)"
          formFieldProps={{
            slotError: errors.description?.message,
          }}
          rows={2}
        />
        <ControlledTextInput
          masked
          useControllerProps={{ control, name: 'value' }}
          name="value"
          label="Value"
          formFieldProps={{
            slotInfo:
              'For security, the secret value will be encrypted and not displayed after creation.',
            slotError: errors.value?.message,
          }}
        />
      </Stack>
    </FormModal>
  );
};
