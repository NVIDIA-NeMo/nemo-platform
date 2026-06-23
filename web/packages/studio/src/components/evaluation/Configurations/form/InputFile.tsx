// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { UploadModal } from '@nemo/common/src/components/UploadModal';
import { Button, FormField, Stack } from '@nvidia/foundations-react-core';
import { DetailRow } from '@studio/components/DetailRow';
import { InputFilePreviewModal } from '@studio/components/evaluation/Configurations/form/InputFile/InputFilePreviewModal';
import { InputFileValidationBanner } from '@studio/components/evaluation/Configurations/form/InputFile/InputFileValidationBanner';
import { InputFileProps } from '@studio/components/evaluation/Configurations/form/InputFile/types';
import { useInputFile } from '@studio/components/evaluation/Configurations/form/InputFile/useInputFile';
import { getDatasetDisplayNameFromFilesUrl } from '@studio/util/files';
import { Plus, File as FileIcon } from 'lucide-react';
import { FC } from 'react';
import { Controller } from 'react-hook-form';

export type { InputFileProps };

export const InputFile: FC<InputFileProps> = ({
  disabled,
  label = 'Input File',
  showTemplatePreview = false,
}) => {
  const {
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
  } = useInputFile();

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
            <InputFileValidationBanner
              isValidating={isValidating}
              fileValidationResult={fileValidationResult}
              fileDetectionResult={fileDetectionResult}
              detectedSchemaType={detectedSchemaType}
              availableKeys={availableKeys}
              control={control}
              setValue={setValue}
              targetMode={targetMode}
              disabled={disabled}
              showTemplatePreview={showTemplatePreview}
              templatePreview={templatePreview}
            />

            <UploadModal
              workspace={workspace}
              open={modalOpen}
              onClose={() => setModalOpen(false)}
              includeDataset
              onSubmit={handleFileSelected}
              submitButtonText="Add selected file"
            />

            {/* File Preview Modal */}
            <InputFilePreviewModal
              open={previewModalOpen}
              onOpenChange={setPreviewModalOpen}
              queryClient={queryClient}
              inputFileUrl={inputFileUrl}
              inputFileFormat={inputFileFormat}
              inputFileDatasetNamespace={inputFileDatasetNamespace}
              inputFileDatasetName={inputFileDatasetName}
              inputFilePath={inputFilePath}
            />
          </Stack>
        );
      }}
    />
  );
};
