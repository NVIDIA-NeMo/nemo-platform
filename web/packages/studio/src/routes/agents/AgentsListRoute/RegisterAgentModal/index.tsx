// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getAgentsListAgentsQueryKey, useAgentsCreateAgent } from '@nemo/sdk/generated/agents/api';
import { Block, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import {
  registerAgentFormSchema,
  type RegisterAgentFormData,
  type RegisterAgentModalProps,
} from '@studio/routes/agents/AgentsListRoute/RegisterAgentModal/type';
import { getAgentDetailRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, useState } from 'react';
import { type SubmitHandler, useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';

const DEFAULT_VALUES: RegisterAgentFormData = { name: '', description: '', url: '' };

export const RegisterAgentModal: FC<RegisterAgentModalProps> = ({ open, onClose, workspace }) => {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [submitError, setSubmitError] = useState<string | undefined>(undefined);

  const {
    mutateAsync: createAgent,
    error: createError,
    isPending,
    reset: resetMutation,
  } = useAgentsCreateAgent({
    mutation: {
      onSuccess: (agent) => {
        toast.success(`Agent "${agent.name}" registered`);
        void queryClient.invalidateQueries({ queryKey: getAgentsListAgentsQueryKey(workspace) });
        resetAndClose();
        if (agent.name) navigate(getAgentDetailRoute(workspace, agent.name));
      },
    },
  });

  const {
    control,
    reset: resetForm,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(registerAgentFormSchema),
    defaultValues: DEFAULT_VALUES,
    disabled: isPending,
    mode: 'onChange',
  });

  const resetAndClose = () => {
    resetMutation();
    setSubmitError(undefined);
    resetForm(DEFAULT_VALUES);
    onClose();
  };

  const onSubmit: SubmitHandler<RegisterAgentFormData> = async (formData) => {
    setSubmitError(undefined);
    try {
      await createAgent({
        workspace,
        data: {
          name: formData.name.trim(),
          description: formData.description?.trim() || '',
          url: formData.url.trim(),
        },
      });
    } catch {
      // surfaced via errorText
    }
  };

  const errorMessage =
    submitError ??
    (createError ? getErrorMessage(createError as Error, 'Failed to register agent') : undefined);

  return (
    <FormModal
      open={open}
      onClose={resetAndClose}
      title="Register Existing Agent"
      submitButtonText="Register"
      onSubmit={handleSubmit(onSubmit)}
      disabled={isPending}
      loading={isPending}
      errorText={errorMessage}
    >
      <ControlledTextInput
        useControllerProps={{ control, name: 'name' }}
        label="Name"
        required
        placeholder="my-nat-agent"
        formFieldProps={{ slotError: errors.name?.message }}
      />
      <ControlledTextInput
        useControllerProps={{ control, name: 'description' }}
        label="Description"
        placeholder="Optional"
        formFieldProps={{ slotError: errors.description?.message }}
      />
      <ControlledTextInput
        useControllerProps={{ control, name: 'url' }}
        label="Agent endpoint URL"
        required
        placeholder="http://localhost:10000"
        formFieldProps={{
          slotError: errors.url?.message,
          slotHelp: (
            <Block>
              <Text kind="body/regular/xs" color="secondary">
                Points at a NAT agent already running (A2A). NeMo Platform fetches its agent card
                and does not run it.
              </Text>
            </Block>
          ),
        }}
      />
    </FormModal>
  );
};
