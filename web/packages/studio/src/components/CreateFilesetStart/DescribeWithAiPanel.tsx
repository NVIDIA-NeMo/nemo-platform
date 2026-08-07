// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useModelSearch } from '@nemo/common/src/api/models/useModelSearch';
import { ControlledTextArea } from '@nemo/common/src/components/form/ControlledTextArea';
import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { ModelSelectV2 } from '@nemo/common/src/components/ModelSelectV2/ModelSelectV2';
import type { ModelSelection } from '@nemo/common/src/components/ModelSelectV2/types';
import { Flex, FormField, Stack } from '@nvidia/foundations-react-core';
import { GeneratedConfigResult } from '@studio/components/CreateFilesetStart/GeneratedConfigResult';
import type { DescribeWithAiPanelProps } from '@studio/components/CreateFilesetStart/types';
import { useDescribeWithAi } from '@studio/components/CreateFilesetStart/useDescribeWithAi';
import { providerForSelection } from '@studio/routes/DataDesignerJobBuildRoute/models';
import type { FC } from 'react';
import { useController } from 'react-hook-form';

const PROMPT_PLACEHOLDER =
  '100 customer support emails, each labelled as phishing or legitimate, with a short reason for the label and the sender domain. Sampled across categories (billing, returns, tech support) with subcategories per category (billing: overcharge, failed payment; returns: damaged item, wrong size)';

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

          <ControlledTextArea
            label="What do you want to generate?"
            required
            rows={8}
            className="w-full resize-y"
            placeholder={PROMPT_PLACEHOLDER}
            disabled={isBusy}
            useControllerProps={{ name: 'prompt', control: form.control }}
          />

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
