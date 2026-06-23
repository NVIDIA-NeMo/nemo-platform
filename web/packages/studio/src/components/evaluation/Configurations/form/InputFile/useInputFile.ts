// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SubmitUploadType } from '@nemo/common/src/components/UploadModal/types';
import { extractUserFriendlyKeysFromRow, getFileRowCount } from '@nemo/common/src/utils/file';
import {
  validateFileFormat,
  detectFileStructure,
  FileValidationResult,
  FileFormatDetectionResult,
} from '@nemo/common/src/utils/fileValidation';
import { datasetFileContentQueryOptions } from '@studio/api/datasets/useDatasetFileContent';
import { buildTemplatePreview } from '@studio/components/evaluation/Configurations/form/InputFile/helpers';
import {
  CreateConfigFormData,
  generateInferenceRequestTemplate,
  useResetConfigForm,
} from '@studio/hooks/evaluation/useCreateConfigurationForm';
import { useFileValidation } from '@studio/hooks/evaluation/useFileValidation';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { logger } from '@studio/util/logger';
import { useQueryClient } from '@tanstack/react-query';
import { useState, useCallback, useEffect, useMemo } from 'react';
import { useFormContext } from 'react-hook-form';

export const useInputFile = () => {
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
    return buildTemplatePreview(inferenceRequestTemplate, templateSelectorInputPrompt);
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

  return {
    control,
    setValue,
    workspace,
    queryClient,
    modalOpen,
    setModalOpen,
    previewModalOpen,
    setPreviewModalOpen,
    isValidating,
    availableKeys,
    targetMode,
    inputFileUrl,
    inputFileFormat,
    inputFileDatasetNamespace,
    inputFileDatasetName,
    inputFilePath,
    fileValidationResult,
    fileDetectionResult,
    detectedSchemaType,
    templatePreview,
    handleRemoveFileClick,
    handleReplaceFileClick,
    handleFileSelected,
  };
};
