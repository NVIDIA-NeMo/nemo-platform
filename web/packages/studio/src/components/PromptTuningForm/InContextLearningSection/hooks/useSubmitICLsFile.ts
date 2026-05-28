// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { compileSystemPrompt } from '@nemo/common/src/models/utils';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { datasetFileContentQueryOptions } from '@studio/api/datasets/useDatasetFileContent';
import { ImportFileContentFormFields } from '@studio/components/ImportFileContent/validation';
import type { PromptTuningFormFields } from '@studio/routes/PromptTuningFormRoute/utils';
import { getFileExtension, parseFileContent, ParseFileContentReturn } from '@studio/util/files';
import { useQueryClient } from '@tanstack/react-query';
import { UseFormReturn, useWatch } from 'react-hook-form';
import { ZodError } from 'zod';

export const useSubmitICLsFile = (
  parentForm: UseFormReturn<PromptTuningFormFields>,
  importFileForm: UseFormReturn<ImportFileContentFormFields>
) => {
  const toast = useToast();
  const queryClient = useQueryClient();
  const currentICLs = useWatch({ control: parentForm.control, name: 'iclFewShotExamples' }) ?? [];
  const systemPromptTemplate =
    useWatch({
      control: parentForm.control,
      name: 'systemPromptTemplate',
    }) ?? '';

  const setICLsFromContent = (content: ParseFileContentReturn, fileName: string) => {
    if (!content.rows.length) {
      throw new ZodError([
        { message: 'No learning examples found in file.', path: ['root'], code: 'custom' },
      ]);
    }
    const newICL = {
      content: content.rows.map((row) => JSON.stringify(row)).join('\n'),
      fileName,
    };
    const hasFileAlready = currentICLs.some((icl) => icl.fileName === fileName);
    const combinedICLs = hasFileAlready
      ? currentICLs.map((icl) => (icl.fileName === fileName ? newICL : icl))
      : [...currentICLs, newICL];
    const iclFewShotExamples = combinedICLs.map((icl) => icl.content).join('\n');
    const { prompt: compiledSystemPrompt, promptTemplate: newSystemPromptTemplate } =
      compileSystemPrompt({
        systemPromptTemplate,
        iclFewShotExamples,
      });
    parentForm.setValue('iclFewShotExamples', combinedICLs, {
      shouldValidate: true,
    });
    parentForm.setValue('systemPrompt', compiledSystemPrompt, { shouldValidate: true });
    parentForm.setValue('systemPromptTemplate', newSystemPromptTemplate, { shouldValidate: true });
  };

  const checkIfFileAlreadyExists = (formData: ImportFileContentFormFields) => {
    const setOfFiles = new Set<string>(currentICLs.map((icl) => icl.fileName));
    const fileExists = formData.file && setOfFiles.has(formData.file.name);
    const datasetFileExists =
      formData.datasetId && formData.filepath && setOfFiles.has(formData.filepath);
    if (fileExists || datasetFileExists) {
      return true;
    }
    return false;
  };

  const onICLsFileSubmit = async (formData: ImportFileContentFormFields): Promise<boolean> => {
    const usedMode = formData.file ? 'file' : 'dataset';
    if (checkIfFileAlreadyExists(formData)) {
      toast.error('File already exists');
      return false;
    }
    try {
      if (formData.file) {
        const text = await formData.file.text();
        setICLsFromContent(
          parseFileContent({
            content: text,
            fileType: getFileExtension(formData.file) ?? '',
          }),
          formData.file.name
        );
        importFileForm.reset();
      } else if (formData.datasetId && formData.filepath) {
        const { workspace, name } = getPartsFromReference(formData.datasetId);
        const queryResult = await queryClient.fetchQuery(
          datasetFileContentQueryOptions({
            workspace,
            name,
            path: formData.filepath,
          })
        );
        setICLsFromContent(
          parseFileContent({
            content: queryResult,
            fileType: getFileExtension(formData.filepath) ?? '',
          }),
          formData.filepath
        );
        importFileForm.reset();
      } else {
        importFileForm.setError('file', { message: 'File or dataset is required' });
        importFileForm.setError('datasetId', { message: 'File or dataset is required' });
        importFileForm.setError('filepath', { message: 'File or dataset is required' });
        return false;
      }
    } catch (error) {
      const errorMessage =
        error instanceof ZodError
          ? (error.errors[0]?.message ?? error.message)
          : ((error as Error).message ?? 'Unexpected error while importing learning examples');

      // Always set the error on the specific field, never on root
      if (usedMode === 'file') {
        importFileForm.setError('file', { message: errorMessage });
      } else {
        importFileForm.setError('filepath', { message: errorMessage });
        importFileForm.setError('datasetId', { message: errorMessage });
      }

      return false;
    }
    return true;
  };
  return onICLsFileSubmit;
};
