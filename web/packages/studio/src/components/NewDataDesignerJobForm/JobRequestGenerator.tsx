/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto.
 */

import { ControlledTextArea } from '@nemo/common/src/components/form/ControlledTextArea';
import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { useChatCompletion } from '@nemo/common/src/hooks/useChatCompletion';
import type { CreateJobRequest as DataDesignerJobRequest } from '@nemo/sdk/generated/data-designer/schema';
import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { DATA_DESIGNER_JOB_GENERATOR_SYSTEM_PROMPT } from '@studio/components/NewDataDesignerJobForm/constants';
import { generateDataDesignerJobRequestTool } from '@studio/components/NewDataDesignerJobForm/tools';
import {
  applyFormModelToJobRequest,
  getErrorMessage,
  getWorkspaceAndModel,
  parseJsonContentToJobRequest,
  parseToolResponseToJobRequest,
  sanitizeJobRequestName,
} from '@studio/components/NewDataDesignerJobForm/utils';
import type { ChatCompletion } from 'openai/resources/index.mjs';
import { useCallback, useMemo, useState } from 'react';
import { type Control, type FieldValues, type Path, useWatch } from 'react-hook-form';

const ERROR_NO_TOOL_CALL =
  'Model did not return a tool call. Try again or choose a different model.';
const ERROR_PARSE_RESPONSE =
  'Failed to parse model response as a Data Designer job request. Try again.';

/**
 * Extract a sanitized job request from the chat completion response, with form model applied.
 * Returns the job request or an error message.
 */
function getJobRequestFromChatResponse(
  response: ChatCompletion,
  modelRef: string,
  provider: string,
  servedModelName: string
): { jobRequest: DataDesignerJobRequest } | { error: string } {
  const message = response.choices[0]?.message;
  const toolCalls = message?.tool_calls;
  if (!toolCalls?.length) {
    return { error: ERROR_NO_TOOL_CALL };
  }
  const rawArgs = toolCalls[0].function.arguments;
  const jobRequest = parseToolResponseToJobRequest(rawArgs);
  if (!jobRequest?.spec?.config) {
    return { error: ERROR_PARSE_RESPONSE };
  }
  const applied = applyFormModelToJobRequest(jobRequest, modelRef, provider, servedModelName);
  return { jobRequest: sanitizeJobRequestName(applied) };
}

export interface JobRequestGeneratorProps<T extends FieldValues = FieldValues> {
  control: Control<T>;
  descriptionName: Path<T>;
  /** Form field holding the (editable) job request JSON. Owned by the parent form. */
  jsonContentName: Path<T>;
  descriptionRules?: object;
  descriptionFormFieldProps?: { slotInfo?: string };
  /** Current workspace (used when modelRef is just a model name with no slash). */
  workspace: string;
  modelRef: string;
  provider: string;
  servedModelName: string;
  /** Write generated JSON back into the parent's jsonContent field. */
  setJsonContent: (value: string) => void;
  disabled?: boolean;
}

/**
 * Generates a Data Designer job request JSON via LLM tool use. Renders the description
 * textarea with Generate button below it, and the JSON editor next to it (side by side).
 * The JSON lives in the parent form's `jsonContentName` field — read here via `useWatch` and
 * written back through `setJsonContent` — so the parent form stays the single source of truth.
 */
export function JobRequestGenerator<T extends FieldValues>({
  control,
  descriptionName,
  jsonContentName,
  descriptionRules,
  descriptionFormFieldProps,
  workspace,
  modelRef,
  provider,
  servedModelName,
  setJsonContent,
  disabled = false,
}: JobRequestGeneratorProps<T>) {
  const description = useWatch({ control, name: descriptionName }) as string;
  const jsonContent = (useWatch({ control, name: jsonContentName }) as string) ?? '';
  const chatCompletion = useChatCompletion();
  const [generationError, setGenerationError] = useState<string | null>(null);

  const parseError = useMemo(() => parseJsonContentToJobRequest(jsonContent).error, [jsonContent]);

  const runGeneration = useCallback(async () => {
    setGenerationError(null);
    const { workspace: chatWorkspace, name: modelName } = getWorkspaceAndModel(modelRef, workspace);

    try {
      const response = (await chatCompletion.mutateAsync({
        workspace: chatWorkspace,
        model: modelName,
        stream: false,
        messages: [
          { role: 'system', content: DATA_DESIGNER_JOB_GENERATOR_SYSTEM_PROMPT },
          { role: 'user', content: description.trim() },
        ],
        tools: [generateDataDesignerJobRequestTool],
        tool_choice: 'required',
      })) as ChatCompletion;

      const result = getJobRequestFromChatResponse(response, modelRef, provider, servedModelName);

      if ('error' in result) {
        setGenerationError(result.error);
        return;
      }

      setJsonContent(JSON.stringify(result.jobRequest, null, 2));
    } catch (err) {
      setGenerationError(getErrorMessage(err, 'Generation failed.'));
    }
  }, [modelRef, provider, servedModelName, workspace, description, chatCompletion, setJsonContent]);

  const hasContent = !!jsonContent.trim();
  const isGenerating = chatCompletion.isPending;

  return (
    <Flex gap="density-xl" className="w-full" direction="row">
      <Stack gap="density-md" className="min-w-0 flex-1">
        <ControlledTextArea
          label="What do you want to generate?"
          required
          placeholder="e.g. Generate synthetic product reviews with columns: product_id, review_text, rating (1-5), and sentiment label."
          rows={10}
          className="w-full"
          useControllerProps={{
            name: descriptionName,
            control,
            rules: descriptionRules,
          }}
          formFieldProps={descriptionFormFieldProps}
        />
        <LoadingButton
          type="button"
          kind="secondary"
          onClick={runGeneration}
          loading={isGenerating}
          disabled={disabled || !description?.trim() || !modelRef}
        >
          {hasContent ? 'Regenerate' : 'Generate'}
        </LoadingButton>
        {generationError && (
          <Text kind="body/regular/sm" className="text-danger">
            {generationError}
          </Text>
        )}
      </Stack>
      <Stack gap="density-sm" className="min-w-0 flex-1">
        <ControlledTextArea
          label="Edit JSON"
          placeholder="Generate to fill..."
          rows={16}
          className="w-full font-mono text-sm"
          useControllerProps={{
            name: jsonContentName,
            control,
          }}
          formFieldProps={{
            slotHelp: 'You can edit the JSON before running Preview or Create job.',
            slotError: parseError ?? undefined,
          }}
        />
      </Stack>
    </Flex>
  );
}
