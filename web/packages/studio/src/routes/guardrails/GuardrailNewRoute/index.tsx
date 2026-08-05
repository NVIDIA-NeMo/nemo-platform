// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal } from '@nemo/common/src/components/FormModal';
import { useGuardrailsCreateConfig } from '@nemo/sdk/generated/platform/api';
import { getErrorMessage } from '@studio/api/common/utils';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getGuardrailDetailRoute, getGuardrailsRoute } from '@studio/routes/utils';
import { type FC } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const NAME_PATTERN = /^[a-z](?!.*--)[a-z0-9\-@.+_]{1,62}(?<!-)$/;

const schema = z.object({
  name: z
    .string()
    .min(1, 'Name is required')
    .regex(
      NAME_PATTERN,
      'Name must start with a lowercase letter, contain only lowercase letters, numbers, hyphens, dots, @, + or _, be 2–63 characters, and not end with a hyphen or contain consecutive hyphens'
    ),
});

type FormData = z.infer<typeof schema>;

export const GuardrailNewRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();

  const {
    control,
    handleSubmit,
    reset,
    formState: { isValid },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { name: '' },
    mode: 'onChange',
  });

  const { mutateAsync: createConfig, isPending, error } = useGuardrailsCreateConfig();

  const handleClose = () => {
    reset();
    navigate(getGuardrailsRoute(workspace));
  };

  const onSubmit = async (data: FormData) => {
    const config = await createConfig({ workspace, data: { name: data.name } });
    navigate(getGuardrailDetailRoute(workspace, config.name ?? data.name));
  };

  return (
    <FormModal
      open
      title="Create Guardrail"
      submitButtonText="Create"
      loading={isPending}
      submitDisabled={!isValid}
      errorText={error ? getErrorMessage(error) : null}
      onSubmit={handleSubmit(onSubmit)}
      onClose={handleClose}
    >
      <ControlledTextInput
        label="Name"
        autoFocus
        disabled={isPending}
        useControllerProps={{ name: 'name', control }}
        attributes={{
          Input: {
            autoComplete: 'off',
            autoCapitalize: 'none',
            autoCorrect: 'off',
            spellCheck: false,
          },
        }}
      />
    </FormModal>
  );
};
