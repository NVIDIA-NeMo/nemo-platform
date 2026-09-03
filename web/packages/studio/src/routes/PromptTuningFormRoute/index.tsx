// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { getErrorMessage } from '@nemo/common/src/api/common/utils';
import { AccessibleTitle } from '@nemo/common/src/components/AccessibleTitle';
import { ChatEmptyState } from '@nemo/common/src/components/Chat/ChatEmptyState';
import { ControlledTextArea } from '@nemo/common/src/components/form/ControlledTextArea';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { FormModal } from '@nemo/common/src/components/FormModal';
import { compileSystemPrompt } from '@nemo/common/src/models/utils';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import {
  getModelsListModelsQueryKey,
  useModelsCreateModel,
  useModelsGetModel,
} from '@nemo/sdk/generated/platform/models';
import {
  AccordionRoot,
  Anchor,
  Button,
  Flex,
  Modal,
  PageHeader,
  Panel,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { queryClient } from '@studio/api/queryClient';
import { Loading } from '@studio/components/Layouts/Loading';
import { ModelChat } from '@studio/components/ModelChat';
import { InContextLearningSection } from '@studio/components/PromptTuningForm/InContextLearningSection';
import { InferenceParametersSection } from '@studio/components/PromptTuningForm/InferenceParametersSection';
import { ModelDetailsSection } from '@studio/components/PromptTuningForm/ModelDetailsSection';
import { ToolsSection } from '@studio/components/PromptTuningForm/ToolsSection';
import { featureFlags } from '@studio/constants/featureFlags';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useModelChatAvailability } from '@studio/hooks/useModelChatAvailability';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import {
  PROMPT_TUNING_HEADING_TEXT,
  SAVE_SUCCESS_MSG,
} from '@studio/routes/PromptTuningFormRoute/constants';
import {
  DEFAULT_PROMPT_TUNING_FORM_VALUES,
  formDataToCreateModelRequest,
  iclDelimiter,
  modelToFormData,
  PromptTuningFormFields,
  promptTuningFormSchema,
} from '@studio/routes/PromptTuningFormRoute/utils';
import { getWorkspaceCustomizationJobListRoute } from '@studio/routes/utils';
import { formatWhitespaceHyphens } from '@studio/util/forms/transforms';
import { ExternalLink, Sliders } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { FormProvider, useForm, useWatch } from 'react-hook-form';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router';

export const PromptTuningFormRoute = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const toast = useToast();
  const location = useLocation();
  const { [ROUTE_PARAMS.modelName]: modelName, [ROUTE_PARAMS.modelNamespace]: modelNamespace } =
    useParams();
  const { state } = location; // Loads pre-filled form values for clone and edit
  const { data: modelApi, isLoading: isLoadingModel } = useModelsGetModel(
    workspace,
    modelName!,
    undefined,
    {
      query: { enabled: !!modelName && !!modelNamespace && !state },
    }
  );

  useBreadcrumbs({
    items: [
      {
        href: getWorkspaceCustomizationJobListRoute(workspace),
        slotLabel: 'Models',
      },
      {
        slotLabel: 'New Prompt-Tuned Model',
      },
    ],
  });
  const [openModal, setOpenModal] = useState<'save' | 'system-prompt-error' | null>(null);
  const { mutate: createModel, isPending: isCreatingModel } = useModelsCreateModel({
    mutation: {
      onSuccess: () => {
        queryClient.resetQueries({ queryKey: getModelsListModelsQueryKey(workspace) });
        toast.success(SAVE_SUCCESS_MSG);
        setOpenModal(null);
        navigate(getWorkspaceCustomizationJobListRoute(workspace));
      },
      onError: (error: Error) => {
        const errorMessage = getErrorMessage(error, 'There was an error saving your model');
        toast.error(errorMessage);
      },
    },
  });
  const [searchParams] = useSearchParams();
  const defaultValues = useMemo(
    () => ({
      ...DEFAULT_PROMPT_TUNING_FORM_VALUES,
      name: generateDefaultName(),
      baseModel: searchParams.get('model') ?? DEFAULT_PROMPT_TUNING_FORM_VALUES.baseModel,
    }),
    [searchParams]
  );
  const values = modelApi ? modelToFormData(modelApi) : (state ?? defaultValues);
  const form = useForm<PromptTuningFormFields>({
    resolver: zodResolver(promptTuningFormSchema),
    values,
    mode: 'onChange',
    disabled: isCreatingModel,
  });
  const baseModel = useWatch({ control: form.control, name: 'baseModel' });
  const systemPromptTemplate = useWatch({ control: form.control, name: 'systemPromptTemplate' });
  const iclFewShotExamplesForm = useWatch({ control: form.control, name: 'iclFewShotExamples' });
  const iclFewShotExamples = iclFewShotExamplesForm?.map((icl) => icl.content).join(iclDelimiter);
  const toolsEnabled = useWatch({ control: form.control, name: 'toolsEnabled' });
  const tools = useWatch({ control: form.control, name: 'tools' });

  const modelNameOnly = (modelName ?? baseModel ?? '').split('/').pop() ?? '';
  // Use the model's own workspace for inference, not necessarily the current URL workspace.
  const inferenceWorkspace = modelNamespace ?? baseModel?.split('/')[0] ?? workspace;

  // Fetch the selected base model entity so we can check its deployment status.
  const { data: baseModelEntity } = useModelsGetModel(
    inferenceWorkspace,
    modelNameOnly,
    undefined,
    { query: { enabled: Boolean(baseModel) } }
  );
  const { modelChatStatus } = useModelChatAvailability(baseModelEntity);

  const systemPromptValidation = form.formState.errors.systemPrompt;
  const validSystemPromptSize = !systemPromptValidation;
  const systemPromptErrorMessage = systemPromptValidation?.message || '';

  const { prompt: compiledSystemPrompt } = compileSystemPrompt({
    systemPromptTemplate,
    iclFewShotExamples,
  });

  const promptData = useMemo(
    () => ({ system_prompt: compiledSystemPrompt }),
    [compiledSystemPrompt]
  );

  const onSubmit = useCallback(
    (data: PromptTuningFormFields) => {
      if (validSystemPromptSize) {
        createModel({ workspace, data: formDataToCreateModelRequest(data, workspace) });
      }
    },
    [validSystemPromptSize, createModel, workspace]
  );

  return (
    <AccessibleTitle title={PROMPT_TUNING_HEADING_TEXT}>
      <FormProvider {...form}>
        <Stack className="w-full h-full p-density-2xl" gap="density-lg">
          <PageHeader
            className="flex-auto"
            slotHeading={PROMPT_TUNING_HEADING_TEXT}
            slotActions={
              <Button
                color="brand"
                onClick={() => {
                  setOpenModal(validSystemPromptSize ? 'save' : 'system-prompt-error');
                }}
              >
                Save Model
              </Button>
            }
          />
          <Flex className="h-full overflow-hidden" justify="center">
            {isLoadingModel ? (
              <Loading />
            ) : (
              <>
                <Panel
                  className="max-w-[450px] h-full rounded-tr-none rounded-br-none overflow-auto [&_.nv-panel-content]:h-full"
                  elevation="high"
                  density="standard"
                  slotHeading={
                    <Flex gap="density-sm">
                      <Sliders />
                      <Text kind="label/bold/lg">Model Parameters</Text>
                    </Flex>
                  }
                >
                  <Stack className="h-full" gap="density-2xl">
                    <ModelDetailsSection />
                    <AccordionRoot
                      multiple
                      defaultValue={['model-details']}
                      className="flex-col -mx-density-2xl border-t border-base [&_:is(.nv-accordion-trigger,.nv-accordion-content)]:px-density-2xl"
                    >
                      {featureFlags.toolCallingEnabled && <InContextLearningSection isEditable />}
                      {featureFlags.toolCallingEnabled && <ToolsSection isEditable />}
                      <InferenceParametersSection />
                    </AccordionRoot>
                    <Anchor
                      kind="standalone"
                      className="flex items-center gap-density-xs"
                      href="https://docs.nvidia.com/nemo/microservices/latest/fine-tune/index.html"
                      target="_blank"
                      rel="noreferrer"
                    >
                      <Text kind="label/bold/sm">Learn more about fine-tuning</Text>
                      <ExternalLink />
                    </Anchor>
                  </Stack>
                </Panel>
                <Panel
                  className="min-w-[300px] flex-1 justify-center border-l-0 rounded-tl-none rounded-bl-none [&_.nv-panel-content]:h-full"
                  elevation="high"
                  density="standard"
                >
                  <Stack className="flex-1 h-full">
                    {modelApi || baseModel ? (
                      <ModelChat
                        model={modelNameOnly}
                        modelChatStatus={modelChatStatus}
                        promptData={promptData}
                        tools={toolsEnabled ? tools : undefined}
                        workspace={inferenceWorkspace}
                        disabled={
                          !baseModel || !validSystemPromptSize || modelChatStatus !== 'enabled'
                        }
                      />
                    ) : (
                      <Stack className="h-full justify-center" align="center">
                        <ChatEmptyState
                          className="h-full w-full"
                          slotHeading="Awaiting Model Selection"
                          slotSubheading="Select a base model to get started"
                        />
                      </Stack>
                    )}
                  </Stack>
                </Panel>
              </>
            )}
          </Flex>
        </Stack>
        {openModal === 'save' && (
          <FormModal
            title="Save Model"
            submitButtonText="Save"
            onSubmit={form.handleSubmit(onSubmit)}
            onClose={() => setOpenModal(null)}
            loading={isCreatingModel}
            open={openModal === 'save'}
          >
            <ControlledTextInput
              useControllerProps={{ name: 'name', control: form.control }}
              label="Model Name"
              required
              selectOnFocus
              onChange={(e) => {
                form.setValue('name', formatWhitespaceHyphens(e), {
                  shouldValidate: true,
                });
              }}
            />
            <ControlledTextArea
              useControllerProps={{ name: 'description', control: form.control }}
              label="Description"
              placeholder="Describe your model"
            />
          </FormModal>
        )}
        {openModal === 'system-prompt-error' && (
          <Modal
            open={openModal === 'system-prompt-error'}
            onOpenChange={() => setOpenModal(null)}
            slotHeading="System Prompt too large"
            slotFooter={
              <Button color="brand" onClick={() => setOpenModal(null)}>
                Dismiss
              </Button>
            }
          >
            <Text>{systemPromptErrorMessage}</Text>
          </Modal>
        )}
      </FormProvider>
    </AccessibleTitle>
  );
};
