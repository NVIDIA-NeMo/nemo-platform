// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledTextArea } from '@nemo/common/src/components/form/ControlledTextArea';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getAgentsListAgentsQueryKey, useAgentsCreateAgent } from '@nemo/sdk/generated/agents/api';
import { Banner, SegmentedControl, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import {
  REGISTRATION_TYPE_EXTERNAL,
  REGISTRATION_TYPE_NAT,
  registerAgentSchema,
  type RegisterAgentFormData,
  workflowConfigFromForm,
} from '@studio/routes/agents/AgentsListRoute/RegisterAgentModal/schema';
import {
  EXTERNAL_ENDPOINT_CONFIG_FORMAT,
  EXTERNAL_ENDPOINT_PROTOCOL,
  NAT_WORKFLOW_CONFIG_FORMAT,
} from '@studio/routes/agents/agentTypes';
import { getAgentDetailRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { type FC } from 'react';
import { type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';

const DEFAULT_VALUES: RegisterAgentFormData = {
  registrationType: REGISTRATION_TYPE_EXTERNAL,
  name: '',
  description: '',
  workflowConfig: '',
  endpointUrl: '',
};

const REGISTRATION_TYPE_ITEMS = [
  { value: REGISTRATION_TYPE_EXTERNAL, children: 'External endpoint' },
  { value: REGISTRATION_TYPE_NAT, children: 'NAT workflow' },
];

interface RegisterAgentModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
}

export const RegisterAgentModal: FC<RegisterAgentModalProps> = ({ open, onClose, workspace }) => {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const {
    mutateAsync: createAgent,
    error: createError,
    isPending,
    reset: resetMutation,
  } = useAgentsCreateAgent();
  const {
    control,
    handleSubmit,
    reset: resetForm,
    setValue,
    formState: { errors },
  } = useForm<RegisterAgentFormData>({
    resolver: zodResolver(registerAgentSchema),
    defaultValues: DEFAULT_VALUES,
    disabled: isPending,
    mode: 'onSubmit',
    reValidateMode: 'onChange',
  });
  const registrationType = useWatch({ control, name: 'registrationType' });

  const resetAndClose = () => {
    resetMutation();
    resetForm(DEFAULT_VALUES);
    onClose();
  };

  const onSubmit: SubmitHandler<RegisterAgentFormData> = async (formData) => {
    const isExternal = formData.registrationType === REGISTRATION_TYPE_EXTERNAL;
    try {
      const agent = await createAgent({
        workspace,
        data: {
          name: formData.name.trim(),
          description: formData.description.trim(),
          config: isExternal
            ? {
                endpoint_url: formData.endpointUrl.trim(),
                protocol: EXTERNAL_ENDPOINT_PROTOCOL,
              }
            : workflowConfigFromForm(formData.workflowConfig),
          config_format: isExternal ? EXTERNAL_ENDPOINT_CONFIG_FORMAT : NAT_WORKFLOW_CONFIG_FORMAT,
        },
      });
      toast.success(`Agent "${agent.name}" registered`);
      await queryClient.invalidateQueries({ queryKey: getAgentsListAgentsQueryKey(workspace) });
      resetAndClose();
      if (agent.name) navigate(getAgentDetailRoute(workspace, agent.name));
    } catch {
      // The mutation error is rendered in the modal.
    }
  };

  return (
    <FormModal
      open={open}
      onClose={resetAndClose}
      title="Register Agent"
      instruction="Register an externally hosted agent for evaluation, or add a NAT workflow that NeMo Platform can deploy and tune."
      submitButtonText="Register"
      onSubmit={handleSubmit(onSubmit)}
      disabled={isPending}
      loading={isPending}
      errorText={
        createError ? getErrorMessage(createError as Error, 'Failed to register agent') : undefined
      }
      className="w-[min(44rem,calc(100vw-2rem))]"
    >
      <SegmentedControl
        className="w-full [&_button]:flex-1"
        value={registrationType}
        onValueChange={(value) =>
          setValue(
            'registrationType',
            value as typeof REGISTRATION_TYPE_EXTERNAL | typeof REGISTRATION_TYPE_NAT,
            { shouldValidate: false }
          )
        }
        items={REGISTRATION_TYPE_ITEMS}
      />
      {registrationType === REGISTRATION_TYPE_EXTERNAL ? (
        <Banner kind="inline" status="info">
          External agents remain hosted outside NeMo Platform. They can be evaluated through their
          endpoint, but the current optimizer cannot change their prompts or hyperparameters.
        </Banner>
      ) : (
        <Banner kind="inline" status="info">
          NAT workflows can be deployed and tuned by NeMo Platform. Agents from another framework
          need a NAT wrapper for managed hyperparameter optimization.
        </Banner>
      )}
      <ControlledTextInput
        useControllerProps={{ control, name: 'name' }}
        label="Agent name"
        placeholder="support-agent"
        required
      />
      <ControlledTextInput
        useControllerProps={{ control, name: 'description' }}
        label="Description"
        placeholder="What this agent does"
      />
      {registrationType === REGISTRATION_TYPE_EXTERNAL ? (
        <>
          <ControlledTextInput
            useControllerProps={{ control, name: 'endpointUrl' }}
            label="Agent endpoint URL"
            placeholder="https://agents.example.com/v1"
            required
          />
          <Text kind="body/regular/xs" color="secondary">
            The endpoint must implement the NAT-compatible HTTP agent contract and be reachable by
            platform jobs. Authenticated external endpoints are not supported by this registration
            contract yet.
          </Text>
        </>
      ) : (
        <>
          <ControlledTextArea
            useControllerProps={{ control, name: 'workflowConfig' }}
            label="NAT workflow YAML"
            placeholder={
              'llms:\n  llm:\n    _type: openai\n    model_name: my-model\nworkflow:\n  _type: react_agent\n  llm_name: llm'
            }
            rows={14}
            required
            formFieldProps={{ slotError: errors.workflowConfig?.message }}
            attributes={{ TextAreaElement: { className: 'font-mono text-sm' } }}
          />
          <Text kind="body/regular/xs" color="secondary">
            Credentials and platform gateway URLs should not be embedded in this config; the
            deployment controller injects platform routing.
          </Text>
        </>
      )}
    </FormModal>
  );
};
