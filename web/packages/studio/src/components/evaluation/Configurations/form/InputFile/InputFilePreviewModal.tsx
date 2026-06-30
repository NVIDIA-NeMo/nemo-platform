// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CodeEditor } from '@nemo/common/src/components/CodeEditor';
import { ContentType } from '@nemo/common/src/components/CodeEditor/constants';
import { Button, Flex, Modal, Text } from '@nvidia/foundations-react-core';
import { datasetFileContentQueryOptions } from '@studio/api/datasets/useDatasetFileContent';
import { CreateConfigFormData } from '@studio/hooks/evaluation/useCreateConfigurationForm';
import { getDatasetDisplayNameFromFilesUrl } from '@studio/util/files';
import { QueryClient } from '@tanstack/react-query';
import { FC } from 'react';

interface InputFilePreviewModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  queryClient: QueryClient;
  inputFileUrl: CreateConfigFormData['configData']['inputFile'];
  inputFileFormat: CreateConfigFormData['configData']['inputFileFormat'];
  inputFileDatasetNamespace: CreateConfigFormData['configData']['inputFileDatasetNamespace'];
  inputFileDatasetName: CreateConfigFormData['configData']['inputFileDatasetName'];
  inputFilePath: CreateConfigFormData['configData']['inputFilePath'];
}

export const InputFilePreviewModal: FC<InputFilePreviewModalProps> = ({
  open,
  onOpenChange,
  queryClient,
  inputFileUrl,
  inputFileFormat,
  inputFileDatasetNamespace,
  inputFileDatasetName,
  inputFilePath,
}) => {
  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      slotHeading={
        inputFileUrl
          ? (getDatasetDisplayNameFromFilesUrl(inputFileUrl) ?? 'File Preview')
          : 'File Preview'
      }
      className="w-[90vw] max-w-[1000px]"
      slotFooter={
        <Flex justify="end" align="center" className="w-full">
          <Button kind="tertiary" onClick={() => onOpenChange(false)}>
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
  );
};
