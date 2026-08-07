// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FormModal } from '@nemo/common/src/components/FormModal';
import { getPartsFromReference } from '@nemo/common/src/namedEntity';
import { handleFormErrorsGeneric } from '@nemo/common/src/utils/forms/error';
import { Banner, Stack } from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import { DatasetFileSelect } from '@studio/components/DatasetFileSelect';
import { DatasetSelect } from '@studio/components/DatasetSelect';
import { FC } from 'react';
import { Controller, FormProvider, useForm, useWatch } from 'react-hook-form';

export interface FormFields {
  datasetId: string;
  filepath: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onSave: (fileContent: string, filepath: string) => void;
}

export const ImportFromDatasetModal: FC<Props> = ({ open, onClose, onSave }) => {
  const formMethods = useForm<FormFields>({
    mode: 'onChange',
  });
  const {
    control,
    handleSubmit,
    formState: { errors, isValid },
  } = formMethods;
  const datasetId = useWatch({ control, name: 'datasetId' });
  const path = useWatch({ control, name: 'filepath' });
  const { workspace, name } = getPartsFromReference(datasetId);
  const {
    data: content,
    error,
    isFetching: isDownloadingFile,
  } = useDatasetFileContent({
    workspace,
    name,
    path,
  });

  const onSaveFileContent = async () => {
    onSave(content ?? '', path);
  };

  return (
    <FormProvider {...formMethods}>
      <FormModal
        open={open}
        title="Import from dataset"
        submitButtonText="Import"
        disabled={isDownloadingFile}
        submitDisabled={!isValid}
        onSubmit={(e) => {
          e.stopPropagation();
          return handleSubmit(
            onSaveFileContent,
            handleFormErrorsGeneric({ title: 'Import From Dataset Form Errors' })
          )(e);
        }}
        onClose={onClose}
      >
        <Stack gap="density-md" className="mb-md">
          <p>
            Import Learning Examples from a dataset. The content of the file you select will
            overwrite the current Learning Examples for this model.
          </p>
          <Controller
            name="datasetId"
            control={control}
            rules={{ required: 'Dataset is required.' }}
            render={({ field: { onChange, value, disabled } }) => (
              <DatasetSelect
                onChange={onChange}
                selectedDatasetId={value}
                disabled={disabled}
                errorText={errors.datasetId?.message}
              />
            )}
          />
          <Controller
            name="filepath"
            control={control}
            rules={{ required: 'File name is required' }}
            render={({ field }) => (
              <DatasetFileSelect
                datasetId={datasetId}
                disabled={field.disabled || !datasetId || isDownloadingFile}
                errorText={errors.filepath?.message}
                hideNew
                helperText="This file's content will be used as this model's Learning Examples"
              />
            )}
          />
          {error && (
            <Banner kind="inline" status="error">
              {`Error importing dataset: ${error}`}
            </Banner>
          )}
        </Stack>
      </FormModal>
    </FormProvider>
  );
};
