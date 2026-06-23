// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  FileValidationResult,
  FileFormatDetectionResult,
} from '@nemo/common/src/utils/fileValidation';
import {
  Banner,
  Block,
  Flex,
  FormField,
  Select,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { EvaluationTargetMode } from '@studio/api/evaluation/types';
import {
  HELP_ICON,
  SUCCESS_CHECK_ICON,
} from '@studio/components/evaluation/Configurations/form/InputFile/constants';
import { buildTemplatePreview } from '@studio/components/evaluation/Configurations/form/InputFile/helpers';
import { CreateConfigFormData } from '@studio/hooks/evaluation/useCreateConfigurationForm';
import { FC } from 'react';
import { Control, Controller, UseFormSetValue } from 'react-hook-form';

interface InputFileValidationBannerProps {
  isValidating: boolean;
  fileValidationResult: FileValidationResult | undefined;
  fileDetectionResult: FileFormatDetectionResult | undefined;
  detectedSchemaType: CreateConfigFormData['configData']['detectedSchemaType'];
  availableKeys: Array<{ label: string; value: string }>;
  control: Control<CreateConfigFormData>;
  setValue: UseFormSetValue<CreateConfigFormData>;
  targetMode: CreateConfigFormData['configData']['targetMode'];
  disabled?: boolean;
  showTemplatePreview: boolean;
  templatePreview: ReturnType<typeof buildTemplatePreview>;
}

export const InputFileValidationBanner: FC<InputFileValidationBannerProps> = ({
  isValidating,
  fileValidationResult,
  fileDetectionResult,
  detectedSchemaType,
  availableKeys,
  control,
  setValue,
  targetMode,
  disabled,
  showTemplatePreview,
  templatePreview,
}) => {
  if (isValidating) {
    return (
      <Banner status="info" kind="inline">
        Validating file format and structure...
      </Banner>
    );
  }

  if (!fileValidationResult) {
    return null;
  }

  if (fileValidationResult.isValid) {
    return (
      <Block padding="density-2xl" className="border-base border-1 rounded-lg">
        <Stack gap="density-md">
          <Text kind="label/bold/md">File Validation</Text>

          {/* File format validation message */}
          <Flex gap="density-md" align="center">
            {SUCCESS_CHECK_ICON}
            <Text kind="body/regular/md">
              {fileValidationResult.format?.toUpperCase()} is valid
            </Text>
          </Flex>

          {/* Schema detection message */}
          <Flex gap="density-md" align="center">
            {detectedSchemaType ? SUCCESS_CHECK_ICON : HELP_ICON}
            <Text kind="body/regular/md">
              {detectedSchemaType
                ? `Detected Schema: ${detectedSchemaType}`
                : 'Schema could not be auto-detected'}
            </Text>
          </Flex>

          {/* Key detection message - only shown if schema is complete */}
          {fileDetectionResult &&
            detectedSchemaType &&
            fileDetectionResult.schemaType !== null &&
            fileDetectionResult.isComplete && (
              <Flex gap="density-md" align="center">
                {SUCCESS_CHECK_ICON}
                <Text kind="body/regular/md">All template strings detected</Text>
              </Flex>
            )}

          {/* Manual mapping interface - shown when schema not detected or incomplete */}
          {(!detectedSchemaType ||
            (fileDetectionResult &&
              fileDetectionResult.schemaType !== null &&
              !fileDetectionResult.isComplete)) &&
            availableKeys.length > 0 && (
              <Stack gap="density-md" className="border-t-base border-t-1 pt-4">
                <Text kind="label/bold/md">Map required keys from your input data</Text>

                <Controller
                  name="configData.inputFileKeyPrompt"
                  control={control}
                  render={({ field, fieldState }) => (
                    <FormField
                      slotLabel="Prompt Key"
                      slotError={fieldState?.error?.message}
                      status={fieldState?.error ? 'error' : undefined}
                    >
                      {({ ...args }) => (
                        <Select
                          {...args}
                          value={field.value || ''}
                          items={[
                            { children: 'Select a key...', value: '' },
                            ...availableKeys.map((key) => ({
                              children: key.label,
                              value: key.value,
                            })),
                          ]}
                          onValueChange={(value: string) => {
                            // Store the original key value in the primary field
                            field.onChange(value);
                            // Also store the interpolated template string
                            const interpolatedValue = value ? `{{item.${value} | trim}}` : '';
                            setValue('configData.templateSelectorInputPrompt', interpolatedValue);
                          }}
                          disabled={disabled}
                          placeholder="Select a key"
                        />
                      )}
                    </FormField>
                  )}
                />

                <Controller
                  name="configData.inputFileKeyGroundTruth"
                  control={control}
                  render={({ field, fieldState }) => (
                    <FormField
                      slotLabel="Ground Truth Key"
                      slotError={fieldState?.error?.message}
                      status={fieldState?.error ? 'error' : undefined}
                    >
                      {({ ...args }) => (
                        <Select
                          {...args}
                          value={field.value || ''}
                          items={[
                            { children: 'Select a key...', value: '' },
                            ...availableKeys.map((key) => ({
                              children: key.label,
                              value: key.value,
                            })),
                          ]}
                          onValueChange={(value: string) => {
                            // Store the original key value in the primary field
                            field.onChange(value);
                            // Also store the interpolated template string
                            const interpolatedValue = value ? `{{item.${value} | trim}}` : '';
                            setValue(
                              'configData.templateSelectorInputGroundTruth',
                              interpolatedValue
                            );
                          }}
                          disabled={disabled}
                          placeholder="Select a key"
                        />
                      )}
                    </FormField>
                  )}
                />

                {/* Output Key - Only shown in offline mode */}
                {targetMode === EvaluationTargetMode.OFFLINE && (
                  <Controller
                    name="configData.inputFileKeyOutput"
                    control={control}
                    render={({ field, fieldState }) => (
                      <FormField
                        slotLabel="Cached Output Key"
                        slotError={fieldState?.error?.message}
                        status={fieldState?.error ? 'error' : undefined}
                      >
                        {({ ...args }) => (
                          <Select
                            {...args}
                            value={field.value || ''}
                            items={[
                              { children: 'Select a key...', value: '' },
                              ...availableKeys.map((key) => ({
                                children: key.label,
                                value: key.value,
                              })),
                            ]}
                            onValueChange={(value: string) => {
                              // Store the original key value in the primary field
                              field.onChange(value);
                              // Also store the interpolated template string
                              const interpolatedValue = value ? `{{item.${value} | trim}}` : '';
                              setValue('configData.templateSelectorOutput', interpolatedValue);
                            }}
                            disabled={disabled}
                            placeholder="Select a key"
                          />
                        )}
                      </FormField>
                    )}
                  />
                )}
              </Stack>
            )}

          {/* Template Preview - shown in all cases when we have valid file */}
          {showTemplatePreview && templatePreview && (
            <Stack gap="density-md" className="border-t-base border-t-1 pt-4">
              <Text kind="label/bold/md">Inference Request Template</Text>
              <pre className="max-h-[400px] w-full overflow-y-auto p-4 border border-base rounded">
                {JSON.stringify(templatePreview, null, 2)}
              </pre>
            </Stack>
          )}
        </Stack>
      </Block>
    );
  }

  return (
    <Banner status="error" kind="inline">
      File validation failed: {fileValidationResult.error}
      <br />
      <small>
        Please ensure your file is valid JSON/JSONL with either messages or prompt-completion
        schema.
      </small>
    </Banner>
  );
};
