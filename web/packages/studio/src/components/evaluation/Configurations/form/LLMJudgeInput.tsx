// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  EVALUATION_DEFAULT_OUTPUT_TEMPLATE_STRING,
  LLM_JUDGE_SCORE_TYPES,
  type LLMJudgeScoreType,
} from '@nemo/common/src/constants/metrics';
import {
  Flex,
  FormField,
  SelectContent,
  SelectItem,
  SelectRoot,
  SelectTrigger,
  Stack,
  TextArea,
  TextInput,
} from '@nvidia/foundations-react-core';
import { EvaluationTargetMode } from '@studio/api/evaluation/types';
import { EvaluationModelSelect } from '@studio/components/evaluation/EvaluationModelSelect';
import {
  CreateConfigFormData,
  generateLLMJudgeUserMessage,
} from '@studio/hooks/evaluation/useCreateConfigurationForm';
import { FC, useEffect } from 'react';
import { Controller, useFormContext, useWatch } from 'react-hook-form';

export const LLMJudgeInput: FC = () => {
  const { control, setValue } = useFormContext<CreateConfigFormData>();

  // Watch for ground truth template to become available
  const templateSelectorInputGroundTruth = useWatch({
    control,
    name: 'configData.templateSelectorInputGroundTruth',
  });

  // Watch for target mode and cached output (for offline mode)
  const targetMode = useWatch({
    control,
    name: 'configData.targetMode',
  });
  const templateSelectorOutput = useWatch({
    control,
    name: 'configData.templateSelectorOutput',
  });

  const isOfflineMode = targetMode === EvaluationTargetMode.OFFLINE;

  /**
   * Synchronize user message with ground truth template for referential integrity.
   *
   * The user message contains template expressions that reference the ground truth field
   * (e.g., {{sample.response}}) and the output field. When these fields change, the user
   * message MUST update to reference the new fields, otherwise the evaluation would be broken.
   *
   * For ONLINE mode: output is {{sample.output_text | trim}} (from model inference)
   * For OFFLINE mode: output is the templateSelectorOutput (from cached file)
   */
  useEffect(() => {
    if (templateSelectorInputGroundTruth) {
      // Determine the correct output text based on mode
      const outputText =
        isOfflineMode && templateSelectorOutput
          ? templateSelectorOutput
          : EVALUATION_DEFAULT_OUTPUT_TEMPLATE_STRING;

      setValue(
        'configData.metricConfigs.llmJudge.userMessage',
        generateLLMJudgeUserMessage(templateSelectorInputGroundTruth, outputText)
      );
    }
    // setValue is stable - only re-run when the other dependencies change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateSelectorInputGroundTruth, templateSelectorOutput, isOfflineMode]);

  return (
    <Stack gap="density-md">
      <Stack gap="density-sm">
        <EvaluationModelSelect
          placeholder="Select a model to use for the LLM judge"
          formFieldName="configData.metricConfigs.llmJudge.model"
          autofillFromSearchParams={false}
        />
      </Stack>

      <Stack gap="density-sm">
        <Controller
          name="configData.metricConfigs.llmJudge.systemMessage"
          control={control}
          render={({ field, fieldState }) => (
            <FormField
              {...field}
              slotLabel="System Message"
              slotError={fieldState.error?.message}
              status={fieldState.error && 'error'}
            >
              {({ status, ...args }) => (
                <TextArea
                  status={status}
                  value={field.value || ''}
                  placeholder="Enter the system message for the LLM judge..."
                  resizeable="manual"
                  attributes={{ TextAreaElement: args }}
                />
              )}
            </FormField>
          )}
        />
        <Controller
          name="configData.metricConfigs.llmJudge.userMessage"
          control={control}
          render={({ field, fieldState }) => (
            <FormField
              {...field}
              slotLabel="User Message"
              slotError={fieldState.error?.message}
              status={fieldState.error && 'error'}
            >
              {({ status, ...args }) => (
                <TextArea
                  status={status}
                  value={field.value || ''}
                  placeholder="Enter the user message template for the LLM judge..."
                  resizeable="manual"
                  rows={4}
                  attributes={{ TextAreaElement: args }}
                />
              )}
            </FormField>
          )}
        />
      </Stack>

      <Stack gap="density-sm">
        <Flex gap="density-md" align="start">
          <Controller
            name="configData.metricConfigs.llmJudge.similarityScoreType"
            control={control}
            render={({ field, fieldState }) => (
              <FormField
                {...field}
                slotLabel="Score Type"
                slotError={fieldState.error?.message}
                status={fieldState.error && 'error'}
                className="w-fit min-w-[140px]"
              >
                {({ ...args }) => (
                  <SelectRoot
                    value={(field.value || 'integer') as LLMJudgeScoreType}
                    onValueChange={field.onChange}
                  >
                    <SelectTrigger placeholder="Select score type" {...args} />
                    <SelectContent>
                      {LLM_JUDGE_SCORE_TYPES.map((type) => (
                        <SelectItem key={type} value={type}>
                          {type}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </SelectRoot>
                )}
              </FormField>
            )}
          />
          <Controller
            name="configData.metricConfigs.llmJudge.similarityScoreParserPattern"
            control={control}
            render={({ field, fieldState }) => (
              <FormField
                {...field}
                slotLabel="Parser Pattern"
                slotError={fieldState.error?.message}
                slotInfo="The pattern to use to parse the score from the LLM response. The first capture group will be used as the score."
                status={fieldState.error && 'error'}
                className="flex-1"
              >
                {({ status, ...args }) => (
                  <TextInput
                    status={status}
                    value={field.value || ''}
                    placeholder="SIMILARITY: (\\d*)"
                    attributes={{ Input: args }}
                  />
                )}
              </FormField>
            )}
          />
        </Flex>
      </Stack>
    </Stack>
  );
};
