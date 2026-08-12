// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Mirrors Studio's SecretsListRoute/CreateSecretModal. Studio's copy lives in a
// route folder rather than @nemo/common, so it is not on the plugin surface;
// promoting it would drag the SDK into the shared vendor bundle every plugin
// loads. The secrets mutation comes off `host.sdk.platform` instead.

import { zodResolver } from '@hookform/resolvers/zod';
import { usePlatformSdk } from '@iron-swarm/api/platform';
import { useToast } from '@iron-swarm/host';
import {
  ControlledTextArea,
  ControlledTextInput,
  ENTITY_NAME_HELP,
  entityNameSchema,
  FormModal,
  getErrorMessage,
  type FormModalProps,
} from '@nemo/common';
import { Stack } from '@nvidia/foundations-react-core';
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
  /** Called with the new secret name so the caller can select it straight away. */
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
  const { useSecretsCreateSecret, getSecretsListSecretsQueryKey } = usePlatformSdk();

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

  const resetAndClose = () => {
    resetCreateMutation();
    resetForm(defaultValues);
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
      // Surfaced through errorText below.
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
