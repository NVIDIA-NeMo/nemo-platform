// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledSearchableSelect } from '@nemo/common/src/components/form/ControlledSearchableSelect';
import { FormModal, type FormModalProps } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getAgentsListAgentsQueryKey, useAgentsCreateAgent } from '@nemo/sdk/generated/agents/api';
import type { Agent } from '@nemo/sdk/generated/agents/schema/Agent';
import { useModelsListModels } from '@nemo/sdk/generated/platform/api';
import { getErrorMessage } from '@studio/api/common/utils';
import {
  hasShownExampleAgentIntro,
  markAgentWalkthroughPending,
  markExampleAgentIntroShown,
} from '@studio/components/sidePanels/AgentPanels/AgentPanel/walkthroughStorage';
import { DEFAULT_LARGE_PAGE_SIZE } from '@studio/constants/constants';
import { getAgentDetailRoute, getAgentsListRoute } from '@studio/routes/utils';
import {
  buildSuggestedModelOptions,
  pickDefaultModelName,
  SUGGESTED_MODEL_GROUP_LABELS,
} from '@studio/util/buildSuggestedModelOptions';
import { useQueryClient } from '@tanstack/react-query';
import { type FC, useEffect, useRef } from 'react';
import { type SubmitHandler, useForm } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';

const EXAMPLE_AGENT_DESCRIPTION = 'A ReAct agent with a calculator and datetime tool.';

const EXAMPLE_AGENT_NAME_PREFIX = 'calculator-demo-agent';

const buildExampleAgentName = (): string =>
  `${EXAMPLE_AGENT_NAME_PREFIX}-${Math.random().toString(36).slice(2, 8)}`;

const isExampleAgentName = (name: string): boolean => name.startsWith(EXAMPLE_AGENT_NAME_PREFIX);

// model_name is concrete: the service doesn't resolve ${NEMO_DEFAULT_MODEL} (only the CLI does).
const buildExampleAgentConfig = (modelName: string): Record<string, unknown> => ({
  function_groups: {
    calculator: { _type: 'calculator' },
  },
  functions: {
    current_datetime: { _type: 'current_datetime' },
  },
  llms: {
    llm: {
      _type: 'openai',
      api_key: 'not-used', // platform overrides at deploy time
      model_name: modelName,
      temperature: 0,
    },
  },
  workflow: {
    _type: 'react_agent',
    tool_names: ['calculator', 'current_datetime'],
    llm_name: 'llm',
    verbose: false,
    parse_agent_response_max_retries: 3,
    use_native_tool_calling: true,
  },
});

const exampleAgentFormSchema = z.object({
  modelName: z.string().min(1, 'Model is required'),
});

type ExampleAgentFormData = z.infer<typeof exampleAgentFormSchema>;

interface CreateExampleAgentModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
  existingAgents: Agent[];
}

export const CreateExampleAgentModal: FC<CreateExampleAgentModalProps> = ({
  open,
  onClose,
  workspace,
  existingAgents,
}) => {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: modelsPage, isLoading: isLoadingModels } = useModelsListModels(
    workspace,
    { page_size: DEFAULT_LARGE_PAGE_SIZE },
    { query: { enabled: open && !!workspace } }
  );
  const models = modelsPage?.data ?? [];
  const modelOptions = buildSuggestedModelOptions(models);

  const {
    mutateAsync: createAgent,
    error: createError,
    isPending,
    reset: resetMutation,
  } = useAgentsCreateAgent({
    mutation: {
      onSuccess: (agent) => {
        toast.success(`Agent "${agent.name}" created`);
        // Refresh the table immediately instead of waiting for its poll interval.
        void queryClient.invalidateQueries({ queryKey: getAgentsListAgentsQueryKey(workspace) });
        const priorExampleAgentExists = existingAgents.some(
          (existing) =>
            !!existing.name && existing.name !== agent.name && isExampleAgentName(existing.name)
        );
        const onboard = !!agent.name && !hasShownExampleAgentIntro() && !priorExampleAgentExists;
        if (onboard && agent.name) {
          markExampleAgentIntroShown();
          markAgentWalkthroughPending(agent.name);
        }
        resetAndClose();
        navigate(
          onboard && agent.name
            ? getAgentDetailRoute(workspace, agent.name)
            : getAgentsListRoute(workspace)
        );
      },
    },
  });

  const {
    control,
    reset: resetForm,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(exampleAgentFormSchema),
    defaultValues: { modelName: '' },
    disabled: isPending,
    mode: 'onChange',
  });

  const seededRef = useRef(false);
  useEffect(() => {
    if (!open) {
      seededRef.current = false;
      resetForm({ modelName: '' });
      return;
    }
    if (seededRef.current) return;
    const defaultModel = pickDefaultModelName(models);
    if (defaultModel) {
      resetForm({ modelName: defaultModel });
      seededRef.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, modelsPage, resetForm]);

  const reset = () => {
    resetMutation();
    resetForm({ modelName: '' });
  };

  const resetAndClose = () => {
    reset();
    onClose();
  };

  const onSubmit: SubmitHandler<ExampleAgentFormData> = async (formData) => {
    try {
      await createAgent({
        workspace,
        data: {
          name: buildExampleAgentName(),
          description: EXAMPLE_AGENT_DESCRIPTION,
          config: buildExampleAgentConfig(formData.modelName),
        },
      });
    } catch {
      // surfaced via errorText
    }
  };

  const errorMessage = createError
    ? getErrorMessage(createError as Error, 'Failed to create example agent')
    : undefined;

  return (
    <FormModal
      open={open}
      onClose={resetAndClose}
      title="Create Example Agent"
      submitButtonText="Create"
      onSubmit={handleSubmit(onSubmit)}
      disabled={isPending}
      loading={isPending}
      errorText={errorMessage}
    >
      <ControlledSearchableSelect
        useControllerProps={{ control, name: 'modelName' }}
        options={modelOptions}
        groupLabels={SUGGESTED_MODEL_GROUP_LABELS}
        isLoading={isLoadingModels}
        triggerPlaceholder="Select a model"
        searchPlaceholder="Search models..."
        emptyMessage={
          isLoadingModels ? 'Loading models...' : 'No usable chat model in this workspace.'
        }
        formFieldProps={{
          slotLabel: 'Model',
          slotError: errors.modelName?.message,
        }}
      />
    </FormModal>
  );
};
