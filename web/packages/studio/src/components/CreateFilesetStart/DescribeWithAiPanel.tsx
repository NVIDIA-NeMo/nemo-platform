// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useModelSearch } from '@nemo/common/src/api/models/useModelSearch';
import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { ModelSelectV2 } from '@nemo/common/src/components/ModelSelectV2/ModelSelectV2';
import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import { Block, Flex, FormField, Stack, TextArea } from '@nvidia/foundations-react-core';
import { PROMPT_SUGGESTIONS } from '@studio/components/CreateFilesetStart/constants';
import { GeneratedConfigResult } from '@studio/components/CreateFilesetStart/GeneratedConfigResult';
import { PromptSuggestionPills } from '@studio/components/CreateFilesetStart/PromptSuggestionPills';
import type { DescribeWithAiPanelProps } from '@studio/components/CreateFilesetStart/types';
import { useDescribeWithAi } from '@studio/components/CreateFilesetStart/useDescribeWithAi';
import { providerForSelection } from '@studio/routes/DataDesignerJobBuildRoute/models';
import type { FC } from 'react';
import { useController } from 'react-hook-form';

const PROMPT_PLACEHOLDER =
  'Describe the rows you want: how many, what each column holds, and how the data should vary. Or start from an example below.';

const MODEL_HELP = 'Needs tool-calling support. This model will be used in LLM columns.';

/**
 * "Describe with AI" detail panel: pick the model that drafts the config, describe the fileset
 * in plain language, and see whether the draft is loadable. The generated config never reaches
 * the builder unvalidated — the parent gates Continue on `onValidConfig` returning a request.
 */
export const DescribeWithAiPanel: FC<DescribeWithAiPanelProps> = ({ workspace, onValidConfig }) => {
  const modelSearch = useModelSearch({ workspace });
  const { form, validation, requestError, rawOutput, pendingAction, generate, requestFix } =
    useDescribeWithAi(workspace, onValidConfig, modelSearch.groups);
  const isBusy = pendingAction !== null;

  const { field: modelField, fieldState: modelState } = useController({
    control: form.control,
    name: 'model',
  });
  const modelValue: ModelSelection | null = modelField.value ? { model: modelField.value } : null;

  const { field: promptField, fieldState: promptState } = useController({
    control: form.control,
    name: 'prompt',
  });
  // Suggestions only make sense on an empty field — once there is text they would cover it.
  const showSuggestions = promptField.value.trim().length === 0 && !isBusy;

  return (
    <form onSubmit={generate} noValidate>
      <Flex gap="density-xl" className="w-full flex-wrap items-stretch">
        <Stack gap="density-md" className="min-w-[320px] flex-1">
          <FormField
            slotLabel="Model"
            slotHelp={MODEL_HELP}
            slotError={modelState.error?.message}
            status={modelState.error ? 'error' : undefined}
            required
          >
            <ModelSelectV2
              {...modelSearch}
              value={modelValue}
              onValueChange={(selection) => {
                modelField.onChange(selection.model);
                form.setValue('provider', providerForSelection(selection));
              }}
              onOpenChange={(isOpen) => {
                if (!isOpen) modelField.onBlur();
              }}
              disabled={isBusy}
              placeholder="Choose a model"
              fullWidth
              dropdownSide="bottom"
              aria-label="Model that drafts the config"
            />
          </FormField>

          <FormField
            slotLabel="What do you want to generate?"
            slotError={promptState.error?.message}
            status={promptState.error ? 'error' : undefined}
            required
          >
            <Block className="relative">
              <TextArea
                rows={8}
                className="w-full resize-y"
                placeholder={PROMPT_PLACEHOLDER}
                disabled={isBusy}
                value={promptField.value}
                onValueChange={promptField.onChange}
                status={promptState.error ? 'error' : undefined}
                attributes={{ TextAreaElement: { onBlur: promptField.onBlur } }}
              />
              {showSuggestions && (
                <PromptSuggestionPills
                  suggestions={PROMPT_SUGGESTIONS}
                  onSelect={(prompt) =>
                    form.setValue('prompt', prompt, { shouldValidate: true, shouldDirty: true })
                  }
                />
              )}
            </Block>
          </FormField>

          <Flex justify="start">
            <LoadingButton
              type="submit"
              kind="secondary"
              loading={pendingAction === 'generate'}
              disabled={isBusy}
            >
              {validation || requestError ? 'Regenerate' : 'Generate'}
            </LoadingButton>
          </Flex>
        </Stack>

        <Stack gap="density-md" className="min-w-[320px] flex-1">
          <GeneratedConfigResult
            validation={validation}
            requestError={requestError}
            rawOutput={rawOutput}
            isGenerating={pendingAction === 'generate'}
            isFixing={pendingAction === 'fix'}
            onFix={() => void requestFix()}
          />
        </Stack>
      </Flex>
    </form>
  );
};
