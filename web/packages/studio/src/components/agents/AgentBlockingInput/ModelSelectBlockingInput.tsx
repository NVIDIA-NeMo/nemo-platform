// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { AgentBlockingInputFrame } from '@studio/components/agents/AgentBlockingInput/AgentBlockingInputFrame';
import type {
  AgentBlockingInputRequest,
  AgentBlockingInputStatus,
  AgentBlockingInputSubmission,
} from '@studio/components/agents/AgentBlockingInput/types';
import { getOutputKey, getStringValue } from '@studio/components/agents/AgentBlockingInput/utils';
import { JudgeModelSelect } from '@studio/components/evaluation/JudgeModelSelect';
import { type FC, useEffect, useMemo } from 'react';
import { FormProvider, useForm } from 'react-hook-form';
import { z } from 'zod';

const getModelSelectSchema = (requiredMessage: string) =>
  z.object({
    model: z.string().trim().min(1, requiredMessage),
  });

type ModelSelectFormData = z.infer<ReturnType<typeof getModelSelectSchema>>;

interface ModelSelectBlockingInputProps {
  readonly input?: Record<string, unknown>;
  readonly onSkip?: () => Promise<void> | void;
  readonly onSubmit: (submission: AgentBlockingInputSubmission) => Promise<void> | void;
  readonly request: AgentBlockingInputRequest;
  readonly status?: AgentBlockingInputStatus;
}

export const ModelSelectBlockingInput: FC<ModelSelectBlockingInputProps> = ({
  input = {},
  onSkip,
  onSubmit,
  request,
  status = 'pending',
}) => {
  const defaultModel =
    getStringValue(input, 'default_model') ?? getStringValue(input, 'model') ?? '';
  const outputKey = getOutputKey(input, 'model');
  const displayLabel = getStringValue(input, 'display_label') ?? 'Selected model';
  const fieldLabel = getStringValue(input, 'field_label') ?? 'Model';
  const placeholder = getStringValue(input, 'placeholder') ?? 'Select a model';
  const requiredMessage = getStringValue(input, 'required_message') ?? 'Model is required';
  const submitLabel = getStringValue(input, 'submit_label') ?? 'Select model';
  const isSubmitting = status === 'submitting';
  const schema = useMemo(() => getModelSelectSchema(requiredMessage), [requiredMessage]);
  const form = useForm<ModelSelectFormData>({
    defaultValues: { model: defaultModel },
    resolver: zodResolver(schema),
    disabled: isSubmitting,
  });
  const selectedModel = form.watch('model');
  const { reset } = form;

  useEffect(() => {
    reset({ model: defaultModel });
  }, [defaultModel, request.id, reset]);

  const submit = form.handleSubmit((data) => {
    return onSubmit({
      displayText: `${displayLabel}: ${data.model}`,
      value: { [outputKey]: data.model },
    });
  });

  return (
    <AgentBlockingInputFrame
      isSubmitting={isSubmitting}
      onSkip={onSkip}
      onSubmit={submit}
      request={request}
      submitDisabled={!selectedModel}
      submitLabel={submitLabel}
    >
      <FormProvider {...form}>
        <JudgeModelSelect<ModelSelectFormData>
          formFieldName="model"
          placeholder={placeholder}
          slotLabel={fieldLabel}
          requiredMessage={requiredMessage}
          dropdownSide="top"
          required
        />
      </FormProvider>
    </AgentBlockingInputFrame>
  );
};
