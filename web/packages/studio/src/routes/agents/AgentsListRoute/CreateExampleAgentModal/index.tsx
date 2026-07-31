// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { ControlledSearchableSelect } from '@nemo/common/src/components/form/ControlledSearchableSelect';
import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { FormModal } from '@nemo/common/src/components/FormModal';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getAgentsListAgentsQueryKey, useAgentsCreateAgent } from '@nemo/sdk/generated/agents/api';
import { useModelsListModels } from '@nemo/sdk/generated/platform/api';
import { loadSampleAgentConfig } from '@studio/api/agents/loadSampleAgentConfig';
import { loadSampleAgentModelName } from '@studio/api/agents/loadSampleAgentModelName';
import { getErrorMessage } from '@studio/api/common/utils';
import {
  hasShownExampleAgentIntro,
  markAgentWalkthroughPending,
  markExampleAgentIntroShown,
} from '@studio/components/sidePanels/AgentPanels/AgentPanel/walkthroughStorage';
import { DEFAULT_LARGE_PAGE_SIZE } from '@studio/constants/constants';
import {
  buildSampleAgentName,
  DEFAULT_SAMPLE_AGENT_KEY,
  getSampleAgent,
  isSampleAgentName,
  SAMPLE_AGENTS,
  sampleAgentFormSchema,
} from '@studio/constants/sampleAgents';
import type {
  CreateExampleAgentModalProps,
  ExampleAgentFormData,
} from '@studio/routes/agents/AgentsListRoute/CreateExampleAgentModal/type';
import { getAgentDetailRoute, getAgentsListRoute } from '@studio/routes/utils';
import {
  buildSuggestedModelOptions,
  pickModelNameForExample,
  SUGGESTED_MODEL_GROUP_LABELS,
} from '@studio/util/buildSuggestedModelOptions';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { type FC, useEffect, useRef, useState } from 'react';
import { type SubmitHandler, useForm, useWatch } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';

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
  const exampleItems = SAMPLE_AGENTS.map((example) => ({
    value: example.key,
    children: example.displayName,
  }));

  const {
    mutateAsync: createAgent,
    error: createError,
    isPending,
    reset: resetMutation,
  } = useAgentsCreateAgent({
    mutation: {
      onSuccess: (agent) => {
        toast.success(`Agent "${agent.name}" created`);
        void queryClient.invalidateQueries({ queryKey: getAgentsListAgentsQueryKey(workspace) });
        const priorExampleAgentExists = existingAgents.some(
          (existing) =>
            !!existing.name && existing.name !== agent.name && isSampleAgentName(existing.name)
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
    setValue,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(sampleAgentFormSchema),
    defaultValues: { exampleKey: DEFAULT_SAMPLE_AGENT_KEY, modelName: '' },
    disabled: isPending,
    mode: 'onChange',
  });

  const exampleKey = useWatch({ control, name: 'exampleKey' });

  const { data: preferredModel } = useQuery({
    queryKey: ['sample-agent-model', exampleKey],
    queryFn: () => loadSampleAgentModelName(getSampleAgent(exampleKey).agentConfigPath),
    enabled: open && !!exampleKey,
    staleTime: Infinity,
  });

  const seededRef = useRef(false);
  useEffect(() => {
    if (!open) {
      seededRef.current = false;
      resetForm({ exampleKey: DEFAULT_SAMPLE_AGENT_KEY, modelName: '' });
      return;
    }
    if (seededRef.current) return;
    const defaultModel = pickModelNameForExample(models, preferredModel);
    if (defaultModel) {
      resetForm({ exampleKey: DEFAULT_SAMPLE_AGENT_KEY, modelName: defaultModel });
      seededRef.current = true;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, modelsPage, preferredModel, resetForm]);

  useEffect(() => {
    if (!open || !seededRef.current) return;
    const nextModel = pickModelNameForExample(models, preferredModel);
    if (nextModel) setValue('modelName', nextModel, { shouldValidate: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [exampleKey, preferredModel]);

  const [loadError, setLoadError] = useState<string | undefined>(undefined);

  const reset = () => {
    resetMutation();
    setLoadError(undefined);
    resetForm({ exampleKey: DEFAULT_SAMPLE_AGENT_KEY, modelName: '' });
  };

  const resetAndClose = () => {
    reset();
    onClose();
  };

  const onSubmit: SubmitHandler<ExampleAgentFormData> = async (formData) => {
    const example = getSampleAgent(formData.exampleKey);
    setLoadError(undefined);
    let config: Record<string, unknown>;
    try {
      config = await loadSampleAgentConfig(example.agentConfigPath, formData.modelName);
    } catch (err) {
      setLoadError(getErrorMessage(err as Error, 'Failed to load example agent config'));
      return;
    }
    try {
      await createAgent({
        workspace,
        data: {
          name: buildSampleAgentName(example.namePrefix),
          description: example.description,
          config,
        },
      });
    } catch {
      // surfaced via errorText
    }
  };

  const errorMessage =
    loadError ??
    (createError
      ? getErrorMessage(createError as Error, 'Failed to create example agent')
      : undefined);

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
      <ControlledSelect
        useControllerProps={{ control, name: 'exampleKey' }}
        items={exampleItems}
        renderValue={(v) => exampleItems.find((item) => item.value === v)?.children}
        formFieldProps={{
          slotLabel: 'Example',
          slotError: errors.exampleKey?.message,
        }}
      />
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
