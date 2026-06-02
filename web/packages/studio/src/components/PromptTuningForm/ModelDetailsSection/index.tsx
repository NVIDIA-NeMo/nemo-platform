// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  type ModelWorkspaceGroup,
  QUERY_PROMPT_TUNEABLE_MODELS,
} from '@nemo/common/src/api/models/useModels';
import { useModelsFromWorkspace } from '@nemo/common/src/api/models/useModelsFromWorkspace';
import { ControlledTextArea } from '@nemo/common/src/components/form/ControlledTextArea';
import { ModelSelectV2, type ModelSelection } from '@nemo/common/src/components/ModelSelectV2';
import { compileSystemPrompt } from '@nemo/common/src/models/utils';
import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import { useModelsGetModel as useGetModel } from '@nemo/sdk/generated/platform/api';
import { FormField, Stack } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import type {
  PromptTuningFormFields,
  PromptTuningFormSectionProps,
} from '@studio/routes/PromptTuningFormRoute/utils';
import { FC, useMemo, useState } from 'react';
import { useController, useFormContext, useWatch } from 'react-hook-form';

export const ModelDetailsSection: FC<
  PromptTuningFormSectionProps & { onModelChange?: (model: string) => void }
> = ({ onModelChange }) => {
  const workspace = useWorkspaceFromPath();
  const [open, setOpen] = useState(false);
  const {
    control,
    formState: { disabled },
    getValues,
    setValue,
  } = useFormContext<PromptTuningFormFields>();

  const { field, fieldState } = useController({
    control,
    name: 'baseModel',
    rules: { required: 'Base model is required' },
  });

  const { groups, isFetching: isLoadingModels } = useModelsFromWorkspace({
    workspace: workspace ?? null,
    query: QUERY_PROMPT_TUNEABLE_MODELS,
    queryOptions: { enabled: open },
  });

  const iclFewShotExamples = useWatch({ control, name: 'iclFewShotExamples' });

  const baseModelFullName = getValues('baseModel');
  const [baseModelNamespace, baseModelName] = baseModelFullName.split('/');
  const { data: baseModel } = useGetModel(baseModelNamespace, baseModelName, undefined, {
    query: {
      enabled: !!baseModelFullName && !open,
    },
  });

  // Ensure the currently selected base model appears in the groups so the
  // dropdown trigger shows the correct name even when the model isn't in
  // the latest results (e.g. before the dropdown has been opened).
  const groupsWithBaseModel = useMemo((): ModelWorkspaceGroup[] => {
    if (!baseModel) return groups;

    const baseModelUrn = getURNFromNamedEntityRef(baseModel);
    const alreadyInGroups = groups.some((g) =>
      g.models.some((m) => getURNFromNamedEntityRef(m) === baseModelUrn)
    );
    if (alreadyInGroups) return groups;

    const targetWorkspace = baseModel.workspace ?? baseModelNamespace;
    const existingGroup = groups.find((g) => g.workspace === targetWorkspace);
    if (existingGroup) {
      return groups.map((g) =>
        g.workspace === targetWorkspace ? { ...g, models: [baseModel, ...g.models] } : g
      );
    }
    return [{ workspace: targetWorkspace, models: [baseModel] }, ...groups];
  }, [groups, baseModel, baseModelNamespace]);

  const value: ModelSelection | null = field.value ? { model: field.value } : null;

  const handleValueChange = (selection: ModelSelection) => {
    field.onChange(selection.model);
    onModelChange?.(selection.model);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) field.onBlur();
  };

  const setCompiledSystemPrompt = (newSystemPromptTemplate: string) => {
    try {
      const compiledSystemPrompt = compileSystemPrompt({
        systemPromptTemplate: newSystemPromptTemplate,
        iclFewShotExamples: iclFewShotExamples?.map((icl) => icl.content).join('\n'),
      }).prompt;
      setValue('systemPrompt', compiledSystemPrompt, { shouldValidate: true });
    } catch {
      // No need to do anything here, RHF's resolver will catch this
    }
  };

  return (
    <Stack gap="density-xl">
      <FormField
        slotLabel="Base Model"
        slotError={fieldState.error?.message}
        slotHelp="The pre-trained model that will be used to build new models within this project."
        required
      >
        <ModelSelectV2
          value={value}
          onValueChange={handleValueChange}
          groups={groupsWithBaseModel}
          loading={isLoadingModels}
          disabled={disabled}
          placeholder={isLoadingModels ? 'Loading models...' : 'Select a model to get started'}
          hideAdapters
          fullWidth
          onOpenChange={handleOpenChange}
        />
      </FormField>
      <ControlledTextArea
        label="System Instructions"
        placeholder="You are a helpful assistant..."
        useControllerProps={{
          name: 'systemPromptTemplate',
          control,
        }}
        formFieldProps={{
          slotInfo: "Add optional system prompt to guide the model's behavior.",
        }}
        onChange={(e) => setCompiledSystemPrompt(e)}
      />
    </Stack>
  );
};
