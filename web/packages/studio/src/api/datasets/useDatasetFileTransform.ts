// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { filesUploadFile } from '@nemo/sdk/generated/platform/api';
import type { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import { invalidateDatasetCaches } from '@studio/api/datasets/invalidateDatasetCaches';
import { renderTemplate } from '@studio/components/transform/renderTemplate';
import { parseFileContent } from '@studio/util/files';
import { useMutation, UseMutationOptions } from '@tanstack/react-query';
import { useCallback } from 'react';

interface MutationProps {
  workspace: string;
  datasetName: string;
  filepath: string;
  /** The `schema_transform` template each row is rewritten through. */
  template: Record<string, unknown>;
  fileContent: string;
  /**
   * Column the template references but the source file does not have. A Data
   * Designer job would declare it as a UUID sampler; here each row gets its own
   * short identifier as it is rewritten.
   */
  generatedIdColumn?: string;
}

type Props = Omit<UseMutationOptions<FilesetFileOutput, Error, MutationProps>, 'mutationFn'>;

/**
 * Rewrites a fileset file in place through a transform template. The mapping is
 * applied in the browser with the same renderer that drives the preview, so what
 * the user approved is exactly what is uploaded.
 */
export const useDatasetFileTransform = ({ onError, onSuccess }: Props) => {
  const toast = useToast();

  const mutationFn = useCallback(
    async ({
      fileContent,
      filepath,
      template,
      workspace,
      datasetName,
      generatedIdColumn,
    }: MutationProps) => {
      const { rows, failures } = parseFileContent({
        content: fileContent,
        fileType: filepath.split('.').at(-1),
      });
      if (failures?.length) {
        toast.error(`${failures.length} Line(s) had parsing errors.`);
      }

      const transformed = rows.map((row) => {
        const input = generatedIdColumn
          ? { ...row, [generatedIdColumn]: crypto.randomUUID().replaceAll('-', '').slice(0, 8) }
          : row;
        return renderTemplate(template, input).row;
      });
      const blob = new Blob([transformed.map((row) => JSON.stringify(row)).join('\n')], {
        type: 'application/json',
      });

      return filesUploadFile(workspace, datasetName, filepath, blob);
    },
    [toast]
  );

  return useMutation({
    mutationFn,
    onError: (data, variables, onMutateResult, context) => {
      onError?.(data, variables, onMutateResult, context);
    },
    onSuccess: (data, variables, onMutateResult, context) => {
      invalidateDatasetCaches(
        variables.workspace,
        variables.datasetName,
        ['files', 'content'],
        variables.filepath
      );
      onSuccess?.(data, variables, onMutateResult, context);
    },
  });
};
