// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  LLMJudgeMetric,
  MetricType as SDKMetricType,
} from '@nemo/sdk/generated/platform/schema';
import { FormField, Stack, TextArea, TextInput } from '@nvidia/foundations-react-core';
import { FC } from 'react';
import { Controller, useFormContext } from 'react-hook-form';

// Subset of metrics currently supported in the UI
export type MetricType = Extract<SDKMetricType, 'llm-judge'>;

export type MetricConfig = LLMJudgeMetric;

interface MetricSelectorProps {
  workspace: string;
}

/**
 * Component for selecting and configuring evaluation metrics
 */
export const MetricSelector: FC<MetricSelectorProps> = () => {
  const { control, watch } = useFormContext();
  const metricType = watch('metricType') as MetricType | undefined;

  return (
    <Stack gap="4">
      {metricType === 'llm-judge' && (
        <Stack gap="4">
          <Controller
            name="metricConfig.scores.0.name"
            control={control}
            rules={{
              required: 'Score name is required',
              pattern: {
                value: /^[a-z0-9_]+$/,
                message: 'Only lowercase letters, numbers, and underscores allowed',
              },
            }}
            render={({ field, fieldState }) => (
              <FormField
                name="score-name"
                slotLabel="Score Name"
                required
                slotHelp="Name for the score (lowercase letters, numbers, and underscores only)"
                status={fieldState.error ? 'error' : undefined}
                slotError={fieldState.error?.message}
              >
                {(props) => (
                  <TextInput
                    {...props}
                    value={field.value ?? ''}
                    onValueChange={field.onChange}
                    attributes={{ Input: { placeholder: 'quality' } }}
                  />
                )}
              </FormField>
            )}
          />

          <Controller
            name="metricConfig.scores.0.description"
            control={control}
            render={({ field }) => (
              <FormField
                name="score-description"
                slotLabel="Score Description (Optional)"
                slotHelp="Human-readable description of what this score measures"
              >
                {(props) => (
                  <TextInput
                    {...props}
                    value={field.value ?? ''}
                    onValueChange={field.onChange}
                    attributes={{
                      Input: { placeholder: 'Overall quality of the response' },
                    }}
                  />
                )}
              </FormField>
            )}
          />

          <div className="grid grid-cols-2 gap-4">
            <Controller
              name="metricConfig.scores.0.minimum"
              control={control}
              rules={{ required: 'Minimum value is required' }}
              render={({ field, fieldState }) => (
                <FormField
                  name="score-minimum"
                  slotLabel="Minimum Value"
                  required
                  slotHelp="Minimum score value"
                  status={fieldState.error ? 'error' : undefined}
                  slotError={fieldState.error?.message}
                >
                  {(props) => (
                    <TextInput
                      {...props}
                      type="number"
                      value={field.value != null ? String(field.value) : ''}
                      onValueChange={(v) => field.onChange(v === '' ? undefined : Number(v))}
                      attributes={{ Input: { placeholder: '1' } }}
                    />
                  )}
                </FormField>
              )}
            />

            <Controller
              name="metricConfig.scores.0.maximum"
              control={control}
              rules={{ required: 'Maximum value is required' }}
              render={({ field, fieldState }) => (
                <FormField
                  name="score-maximum"
                  slotLabel="Maximum Value"
                  required
                  slotHelp="Maximum score value"
                  status={fieldState.error ? 'error' : undefined}
                  slotError={fieldState.error?.message}
                >
                  {(props) => (
                    <TextInput
                      {...props}
                      type="number"
                      value={field.value != null ? String(field.value) : ''}
                      onValueChange={(v) => field.onChange(v === '' ? undefined : Number(v))}
                      attributes={{ Input: { placeholder: '5' } }}
                    />
                  )}
                </FormField>
              )}
            />
          </div>

          <Controller
            name="metricConfig.prompt_template"
            control={control}
            render={({ field }) => (
              <FormField
                name="judge-prompt-template"
                slotLabel="Prompt Template (Optional)"
                slotHelp={
                  <>
                    Custom prompt for the judge. Use template variables like{' '}
                    <code>{'{{input}}'}</code> and <code>{'{{output}}'}</code>. Leave empty for
                    auto-generated prompt.
                  </>
                }
              >
                {(props) => (
                  <TextArea
                    {...props}
                    value={field.value ?? ''}
                    onValueChange={field.onChange}
                    resizeable="manual"
                    attributes={{
                      TextAreaElement: {
                        className: 'font-mono text-sm',
                        rows: 4,
                        placeholder:
                          'System message and instructions for the judge LLM.\nUse {{input}} and {{output}} to reference the data.',
                      },
                    }}
                  />
                )}
              </FormField>
            )}
          />

          <Controller
            name="metricConfig.scores.0.parser.pattern"
            control={control}
            render={({ field }) => (
              <FormField
                name="parser-pattern"
                slotLabel="Parser Pattern (Optional)"
                slotHelp="Regex pattern to extract score from judge response. Leave empty to use JSON parser with the score name as the key."
              >
                {(props) => (
                  <TextInput
                    {...props}
                    value={field.value ?? ''}
                    onValueChange={field.onChange}
                    attributes={{
                      Input: {
                        className: 'font-mono',
                        placeholder: 'Leave empty to use JSON parser',
                      },
                    }}
                  />
                )}
              </FormField>
            )}
          />
        </Stack>
      )}
    </Stack>
  );
};
