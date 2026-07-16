// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledTextArea } from '@nemo/common/src/components/form/ControlledTextArea';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getAgentsListAgentsQueryKey, useAgentsCreateAgent } from '@nemo/sdk/generated/agents/api';
import { Anchor, Block, SegmentedControl, Text } from '@nvidia/foundations-react-core';
import { parseAgentConfig } from '@studio/api/agents/parseAgentConfig';
import { getErrorMessage } from '@studio/api/common/utils';
import { LINK_DOCS_AGENTS } from '@studio/constants/links';
import {
  registerAgentFormSchema,
  type RegisterAgentFormData,
  type RegisterAgentModalProps,
} from '@studio/routes/agents/AgentsListRoute/RegisterAgentModal/type';
import { getAgentDetailRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, useState } from 'react';
import { type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';

const DEFAULT_VALUES: RegisterAgentFormData = {
  mode: 'url',
  name: '',
  description: '',
  url: '',
  configText: '',
};

const MODE_ITEMS = [
  { value: 'url', children: 'Connect running agent' },
  { value: 'config', children: 'Paste config' },
];

export const RegisterAgentModal: FC<RegisterAgentModalProps> = ({ open, onClose, workspace }) => {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [parseError, setParseError] = useState<string | undefined>(undefined);

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

  const mode = useWatch({ control, name: 'mode' });

  const resetAndClose = () => {
    resetMutation();
    setParseError(undefined);
    resetForm(DEFAULT_VALUES);
    onClose();
  };

  const onSubmit: SubmitHandler<RegisterAgentFormData> = async (formData) => {
    setParseError(undefined);
    const description = formData.description?.trim() || '';

    let data: Parameters<typeof createAgent>[0]['data'];
    if (formData.mode === 'url') {
      data = { name: formData.name.trim(), description, url: formData.url?.trim() };
    } else {
      let config: Record<string, unknown>;
      try {
        config = parseAgentConfig(formData.configText ?? '');
      } catch (err) {
        setParseError((err as Error).message);
        return;
      }
      data = { name: formData.name.trim(), description, config };
    }

    try {
      await createAgent({ workspace, data });
    } catch {
      // surfaced via errorText
    }
  };

  const errorMessage =
    parseError ??
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
      <SegmentedControl
        className="w-full!"
        value={mode}
        items={MODE_ITEMS}
        onValueChange={(v) =>
          resetForm({ ...DEFAULT_VALUES, mode: v as RegisterAgentFormData['mode'] })
        }
      />

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

      {mode === 'url' ? (
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
      ) : (
        <ControlledTextArea
          useControllerProps={{ control, name: 'configText' }}
          label="NAT workflow config (YAML)"
          rows={12}
          placeholder={'workflow:\n  _type: react_agent\n  ...'}
          formFieldProps={{
            slotError: errors.configText?.message,
            slotHelp: (
              <Anchor href={LINK_DOCS_AGENTS} target="_blank" rel="noopener noreferrer">
                How to structure a NAT workflow config
              </Anchor>
            ),
          }}
        />
      )}
    </FormModal>
  );
};
