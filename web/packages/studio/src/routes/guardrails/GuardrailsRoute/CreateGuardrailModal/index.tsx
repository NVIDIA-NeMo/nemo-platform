// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal } from '@nemo/common/src/components/FormModal';
import { ENTITY_NAME_HELP, entityNameSchema } from '@nemo/common/src/utils/entityName';
import { useGuardrailsCreateConfig } from '@nemo/sdk/generated/platform/api';
import { getErrorMessage } from '@studio/api/common/utils';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getGuardrailDetailRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { type FC } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate } from 'react-router';
import { z } from 'zod';

const schema = z.object({
  name: entityNameSchema(),
});

type FormData = z.infer<typeof schema>;

interface Props {
  open: boolean;
  onClose: () => void;
}

export const CreateGuardrailModal: FC<Props> = ({ open, onClose }) => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

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

  const {
    mutateAsync: createConfig,
    isPending,
    error,
    reset: resetMutation,
  } = useGuardrailsCreateConfig();

  const handleClose = () => {
    reset();
    resetMutation();
    onClose();
  };

  const onSubmit = async (data: FormData) => {
    const config = await createConfig({ workspace, data: { name: data.name } });
    await queryClient.invalidateQueries({
      queryKey: [`/apis/guardrails/v2/workspaces/${workspace}/configs`],
    });
    handleClose();
    navigate(getGuardrailDetailRoute(workspace, config.name ?? data.name));
  };

  return (
    <FormModal
      open={open}
      title="Create Guardrail"
      submitButtonText="Create"
      disabled={isPending}
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
        formFieldProps={{ slotInfo: ENTITY_NAME_HELP }}
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
