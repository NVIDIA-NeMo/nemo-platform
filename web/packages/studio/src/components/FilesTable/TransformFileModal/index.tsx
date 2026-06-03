// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { MappingFields } from '@nemo/common/src/components/form/MappingFields';
import { FormModal } from '@nemo/common/src/components/FormModal';
import { ModelSelect } from '@nemo/common/src/components/ModelSelect';
import { getEntityReference, getPartsFromReference } from '@nemo/common/src/namedEntity';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { useModelsListModels } from '@nemo/sdk/generated/platform/api';
import {
  CodeSnippet,
  Divider,
  Flex,
  Label,
  Spinner,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { useDatasetFileContent } from '@studio/api/datasets/useDatasetFileContent';
import { useDatasetFileTransform } from '@studio/api/datasets/useDatasetFileTransform';
import {
  TransformFileFormFields,
  transformFileSchema,
} from '@studio/components/FilesTable/TransformFileModal/types';
import { InfoTooltip } from '@studio/components/InfoTooltip';
import { ValueWithLabel } from '@studio/components/ValueWithLabel';
import { useSelectedDatasetId } from '@studio/hooks/useSelectedDatasetId';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getContentSchema } from '@studio/util/files';
import { handleFormErrorsGeneric } from '@studio/util/forms/error';
import { GitBranch } from 'lucide-react';
import { ComponentProps, FC, useMemo } from 'react';
import { useForm, useWatch } from 'react-hook-form';

interface Props extends Pick<ComponentProps<typeof FormModal>, 'open' | 'onClose'> {
  filepath?: string;
}

/**
 * This modal is used to handle transforms to a file's schema
 * such as manipulating columns and adding model completions.
 */
export const TransformFileModal: FC<Props> = ({ open, onClose, filepath }) => {
  const toast = useToast();
  const datasetId = useSelectedDatasetId();
  const datasetNameSplit = getPartsFromReference(datasetId);
  const workspace = useWorkspaceFromPath();

  // Form Fields
  const { control, reset, handleSubmit } = useForm<TransformFileFormFields>({
    mode: 'onChange',
    resolver: zodResolver(transformFileSchema),
    defaultValues: {
      filepath,
      mappings: [],
    },
  });
  const filepathForm = useWatch({ control, name: 'filepath' });
  const resetAndClose = () => {
    reset();
    onClose();
  };

  const { data: modelsResponse, isFetching: isFetchingModels } = useModelsListModels(workspace, {
    page_size: 1000,
    sort: 'created_at',
  });
  const models = useMemo(() => {
    return modelsResponse?.data;
  }, [modelsResponse]);

  const { data: fileContent, isLoading: isLoadingFileContent } = useDatasetFileContent({
    ...datasetNameSplit,
    path: filepathForm,
  });
  const { schema, total_rows } = useMemo(() => {
    return getContentSchema(fileContent, {
      fileType: filepathForm.split('.').at(-1) ?? '',
    });
  }, [filepathForm, fileContent]);

  const { mutate: transformFile, isPending } = useDatasetFileTransform({
    onSuccess: () => {
      toast.success('Successfully finished file transformation!');
      resetAndClose();
    },
  });

  const onSubmit = (data: TransformFileFormFields) => {
    const model = models?.find((model) => getEntityReference(model) === data.model);
    if (!fileContent) {
      toast.error('File content not found');
      return;
    }
    if (!model && data.model) {
      toast.error('Model not found');
      return;
    }
    transformFile({
      workspace: datasetNameSplit.workspace,
      datasetName: datasetNameSplit.name,
      filepath: filepathForm,
      mappings: data.mappings.filter((m) => m.key.trim() !== ''),
      fileContent: fileContent,
      model,
    });
  };

  return (
    <FormModal
      open={open}
      title={
        <Flex gap="density-md" align="center">
          <GitBranch />
          Transform
        </Flex>
      }
      submitButtonText="Confirm"
      onSubmit={handleSubmit(
        onSubmit,
        handleFormErrorsGeneric({ title: 'Transform File Form Errors' })
      )}
      onClose={resetAndClose}
      disabled={isPending}
      submitDisabled={isLoadingFileContent}
      loading={isPending}
    >
      <Stack gap="density-xl">
        <Text className="leading-normal">
          Map existing columns to new names, add computed fields, and optionally run inference
          models on each row to enhance your data with AI-generated content.
        </Text>
        <ValueWithLabel
          labelProps={{ className: 'font-bold' }}
          label="Source File"
          value={filepath}
        />
        <Divider />
        {isLoadingFileContent ? (
          <Flex justify="center" align="center" className="h-full py-[80px]">
            <Spinner description="Loading file content..." />
          </Flex>
        ) : (
          <Stack gap="density-xl" className="pb-4">
            <CodeSnippet
              value={JSON.stringify(schema, null, 2)}
              language="json"
              kind="block"
              attributes={{
                CodeSnippetCopyButton: {
                  type: 'button',
                  onClick: () => {
                    toast.success('Schema copied to clipboard!');
                  },
                },
              }}
              slotActions={
                <Flex className="w-full" justify="between">
                  <Label className="font-bold">Schema ({total_rows ?? 0} rows)</Label>
                  <InfoTooltip message="The schema of the source file." />
                </Flex>
              }
            />
            <MappingFields
              control={control}
              name="mappings"
              disabled={isLoadingFileContent}
              schema={schema}
            />
            <ModelSelect
              tooltip="Runs inference on EACH ROW of the file. Please ensure your file schema uses 'prompt', 'instruction', or 'question' as your user message key."
              models={models}
              loading={isFetchingModels}
              formFieldProps={{
                slotLabel: <Label className="font-bold">Model for Inference</Label>,
              }}
              useControllerProps={{ control, name: 'model' }}
            />
          </Stack>
        )}
      </Stack>
    </FormModal>
  );
};
