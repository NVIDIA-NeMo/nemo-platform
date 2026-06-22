// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeEditor } from '@nemo/common/src/components/CodeEditor';
import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import { UploadModal } from '@nemo/common/src/components/UploadModal';
import { SubmitUploadType } from '@nemo/common/src/components/UploadModal/types';
import { extractUserFriendlyKeysFromRow, getFileRowCount } from '@nemo/common/src/utils/file';
import {
  validateFileFormat,
  detectFileStructure,
  FileValidationResult,
  FileFormatDetectionResult,
} from '@nemo/common/src/utils/fileValidation';
import {
  Banner,
  Block,
  Button,
  Flex,
  FormField,
  Modal,
  Select,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { datasetFileContentQueryOptions } from '@studio/api/datasets/useDatasetFileContent';
import { EvaluationTargetMode } from '@studio/api/evaluation/types';
import { DetailRow } from '@studio/components/DetailRow';
import {
  CreateConfigFormData,
  generateInferenceRequestTemplate,
  useResetConfigForm,
} from '@studio/hooks/evaluation/useCreateConfigurationForm';
import { useFileValidation } from '@studio/hooks/evaluation/useFileValidation';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getDatasetDisplayNameFromFilesUrl } from '@studio/util/files';
import { logger } from '@studio/util/logger';
import { useQueryClient } from '@tanstack/react-query';
import { Plus, CircleCheck, CircleHelp, File as FileIcon } from 'lucide-react';
import { FC, useState, useCallback, useEffect, useMemo } from 'react';
import { Controller, useFormContext } from 'react-hook-form';

export interface InputFileProps {
  disabled?: boolean;
  /** Label for the input file field. Defaults to "Input File" */
  label?: string;
  /** Whether to show the inference request template preview. Defaults to false */
  showTemplatePreview?: boolean;
}

const SUCCESS_CHECK_ICON = <CircleCheck color="var(--text-color-feedback-success)" />;
const HELP_ICON = <CircleHelp color="var(--text-color-subtle)" />;

export const InputFile: FC<InputFileProps> = ({
  disabled,
  label = 'Input File',
  showTemplatePreview = false,
}) => {
  const { control, resetField, setValue, watch } = useFormContext<CreateConfigFormData>();
  const [modalOpen, setModalOpen] = useState(false);
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [availableKeys, setAvailableKeys] = useState<Array<{ label: string; value: string }>>([]);
  const workspace = useWorkspaceFromPath();
  const queryClient = useQueryClient();

  // Hook to reset form while preserving key fields
  const resetConfigForm = useResetConfigForm();

  // Watch firstRowData from form instead of local state
  const firstRowData = watch('configData.firstRowData');
  const targetMode = watch('configData.targetMode');
  const inputFileUrl = watch('configData.inputFile');

  // Watch file metadata for preview
  const inputFileFormat = watch('configData.inputFileFormat');
  const inputFileDatasetNamespace = watch('configData.inputFileDatasetNamespace');
  const inputFileDatasetName = watch('configData.inputFileDatasetName');
  const inputFilePath = watch('configData.inputFilePath');

  // Use the file validation hook
  const { updateFormFromFile } = useFileValidation({ setValue });

  // Watch for validation results to display them
  const fileValidationResult = watch('configData.fileValidationResult') as
    | FileValidationResult
    | undefined;
  const fileDetectionResult = watch('configData.fileDetectionResult') as
    | FileFormatDetectionResult
    | undefined;
  const detectedSchemaType = watch('configData.detectedSchemaType');
  const inferenceRequestTemplate = watch('configData.inferenceRequestTemplate');
  const templateSelectorInputPrompt = watch('configData.templateSelectorInputPrompt');

  // Build template preview - only show if prompt is set
  const templatePreview = useMemo(() => {
    // Template preview requires at minimum a prompt to be set
    if (!templateSelectorInputPrompt?.trim()) {
      return null;
    }

    if (inferenceRequestTemplate) {
      return {
        messages: inferenceRequestTemplate.messages,
      };
    }

    return {
      messages: [{ role: 'user', content: templateSelectorInputPrompt }],
    };
  }, [inferenceRequestTemplate, templateSelectorInputPrompt]);

  // Helper function to clear all file-related fields
  const clearFileRelatedFields = useCallback(() => {
    // Reset form to defaults while preserving key fields
    resetConfigForm();

    // Clear local component state
    setAvailableKeys([]);
    setIsValidating(false);
  }, [resetConfigForm]);

  const handleRemoveFileClick = () => {
    resetField('configData.inputFile');
    clearFileRelatedFields();
  };

  const handleReplaceFileClick = () => setModalOpen(true);

  // Extract available keys when we have first row data
  useEffect(() => {
    if (firstRowData) {
      try {
        const keys = extractUserFriendlyKeysFromRow(firstRowData);
        setAvailableKeys(keys);
      } catch {
        setAvailableKeys([]);
      }
    } else {
      setAvailableKeys([]);
    }
  }, [firstRowData]);

  // Regenerate inference request template when prompt changes
  useEffect(() => {
    if (templateSelectorInputPrompt?.trim()) {
      const template = generateInferenceRequestTemplate(templateSelectorInputPrompt);
      setValue('configData.inferenceRequestTemplate', template);
    } else {
      setValue('configData.inferenceRequestTemplate', undefined);
    }
  }, [templateSelectorInputPrompt, setValue]);

  // Helper function to render validation banner
  const renderValidationBanner = () => {
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

  const handleFileSelected = useCallback(
    async (file: SubmitUploadType) => {
      if (file.type === 'file') return;

      // Clear previous file-related values when changing files
      clearFileRelatedFields();

      // Set the file URL first
      setValue('configData.inputFile', file.url);
      setIsValidating(true);

      try {
        // Fetch and cache the file content using TanStack Query
        // This will cache it for pagination without re-downloading
        const fileContent = await queryClient.fetchQuery(
          datasetFileContentQueryOptions({
            workspace: file.dataset.workspace!,
            name: file.dataset.name!,
            path: file.path,
          })
        );

        // Create a File object from the downloaded content
        const fileName = file.path.split('/').pop() || 'file';
        const fileObj = new File([fileContent], fileName, { type: 'application/json' });

        // Validate file format
        const validationResult = await validateFileFormat(fileObj);

        if (validationResult.isValid && validationResult.format) {
          // Detect file structure
          const detectionResult = await detectFileStructure(
            fileObj,
            validationResult.format,
            targetMode
          );

          // Store first row for manual mapping (from detection result if available)
          setValue('configData.firstRowData', detectionResult?.firstRow || null);

          // Get total row count for pagination
          const rowCount = await getFileRowCount(fileObj, validationResult.format);
          setValue('configData.inputFileTotalRowCount', rowCount);
          setValue('configData.inputFileCurrentRowIndex', 0);

          // Store file metadata for later pagination
          setValue('configData.inputFileFormat', validationResult.format as 'json' | 'jsonl');
          setValue('configData.inputFileDatasetNamespace', file.dataset.workspace!);
          setValue('configData.inputFileDatasetName', file.dataset.name!);
          setValue('configData.inputFilePath', file.path);

          // Use the validation hook to update form fields
          updateFormFromFile(validationResult, detectionResult || undefined);
        } else {
          // Use the validation hook to handle invalid files
          setValue('configData.firstRowData', null);
          updateFormFromFile(validationResult, undefined);
        }
      } catch (error) {
        logger.error('Failed to validate selected file', error);
        // Create error validation result
        const errorResult: FileValidationResult = {
          isValid: false,
          format: null,
          error: `Failed to validate file: ${error instanceof Error ? error.message : 'Unknown error'}`,
        };
        updateFormFromFile(errorResult, undefined);
      } finally {
        setIsValidating(false);
      }
    },
    [setValue, updateFormFromFile, clearFileRelatedFields, targetMode, queryClient]
  );

  return (
    <Controller
      name="configData.inputFile"
      control={control}
      disabled={disabled}
      rules={{ onChange: () => setModalOpen(false) }}
      render={({ field, fieldState }) => {
        return (
          <Stack gap="density-md">
            <Stack gap="density-xs">
              <FormField
                slotLabel={label}
                {...field}
                slotError={fieldState?.error?.message}
                status={fieldState?.error ? 'error' : undefined}
              >
                {field.value ? (
                  <DetailRow
                    label={getDatasetDisplayNameFromFilesUrl(field.value) ?? field.value}
                    onDelete={handleRemoveFileClick}
                    onView={() => setPreviewModalOpen(true)}
                    icon={<FileIcon />}
                    isEditable={!field.disabled}
                    disabled={field.disabled}
                  />
                ) : (
                  <Button
                    kind="secondary"
                    type="button"
                    onClick={handleReplaceFileClick}
                    disabled={field.disabled}
                    className={`w-full ${fieldState?.error ? 'border-red-500' : ''}`}
                  >
                    <Plus />
                    Select File
                  </Button>
                )}
              </FormField>
            </Stack>

            {/* Validation Feedback */}
            {renderValidationBanner()}

            <UploadModal
              workspace={workspace}
              open={modalOpen}
              onClose={() => setModalOpen(false)}
              includeDataset
              onSubmit={handleFileSelected}
              submitButtonText="Add selected file"
            />

            {/* File Preview Modal */}
            <Modal
              open={previewModalOpen}
              onOpenChange={setPreviewModalOpen}
              slotHeading={
                inputFileUrl
                  ? (getDatasetDisplayNameFromFilesUrl(inputFileUrl) ?? 'File Preview')
                  : 'File Preview'
              }
              className="w-[90vw] max-w-[1000px]"
              slotFooter={
                <Flex justify="end" align="center" className="w-full">
                  <Button kind="tertiary" onClick={() => setPreviewModalOpen(false)}>
                    Close
                  </Button>
                </Flex>
              }
            >
              {(() => {
                // Get the cached file content from TanStack Query
                if (!inputFileDatasetNamespace || !inputFileDatasetName || !inputFilePath) {
                  return <Text>No file selected</Text>;
                }

                const cachedFileContent = queryClient.getQueryData<string>(
                  datasetFileContentQueryOptions({
                    workspace: inputFileDatasetNamespace,
                    name: inputFileDatasetName,
                    path: inputFilePath,
                  }).queryKey
                );

                if (!cachedFileContent) {
                  return <Text>File content not available</Text>;
                }

                return (
                  <CodeEditor
                    contentType={inputFileFormat === 'json' ? ContentType.JSON : ContentType.JSONL}
                    content={cachedFileContent}
                    readOnly
                  />
                );
              })()}
            </Modal>
          </Stack>
        );
      }}
    />
  );
};
