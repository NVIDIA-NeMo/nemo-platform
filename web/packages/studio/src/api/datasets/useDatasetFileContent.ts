// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { filesDownloadFile, filesHeadFile } from '@nemo/sdk/generated/platform/api';
import { EntityIdentifier } from '@studio/api/common/types';
import { PREVIEWABLE_FILE_TYPES } from '@studio/api/datasets/constants';
import { getDatasetFileContentQueryKey } from '@studio/api/datasets/invalidateDatasetCaches';
import { queryOptions, useQuery, UseQueryOptions, useSuspenseQuery } from '@tanstack/react-query';
import { parquetRead } from 'hyparquet';

interface UseDatasetFileContentParams extends Required<EntityIdentifier> {
  path: string;
  range?: [number, number];
}

export type UseDatasetFilesOptions = Omit<UseQueryOptions<string, Error>, 'queryFn' | 'queryKey'> &
  UseDatasetFileContentParams;

export const datasetFileContentQueryOptions = ({
  workspace,
  name,
  path,
  range,
}: UseDatasetFileContentParams) =>
  queryOptions<string, Error>({
    staleTime: Infinity, // We should prevent refetching full files (costly) unless directly invalidated
    queryKey: [
      ...getDatasetFileContentQueryKey(workspace!, name, path),
      ...(range ? range.map((bound) => String(bound)) : []),
    ],
    queryFn: async () => {
      if (!path.includes('.') || !PREVIEWABLE_FILE_TYPES.has(path.split('.').at(-1)!)) {
        throw new Error(
          `Unsupported file type. Currently supports: ${[...PREVIEWABLE_FILE_TYPES].join(', ')}`
        );
      }

      // Check if file exists
      try {
        await filesHeadFile(workspace!, name, path);
      } catch {
        throw new Error('Unable to find base file.');
      }

      if (path.endsWith('parquet')) {
        try {
          let data: string = '';
          // Use SDK so the request includes auth (Bearer token). asyncBufferFromUrl does a raw fetch with no credentials → 401.
          const blob = await filesDownloadFile(workspace!, name, path);
          if (!blob) throw new Error('Invalid response while downloading parquet file');
          const buffer = await blob.arrayBuffer();
          await parquetRead({
            file: buffer,
            rowFormat: 'object',
            rowStart: range?.[0],
            rowEnd: range?.[1],
            onComplete: (content) => {
              for (const row of content) {
                data += `${JSON.stringify(row)}\n`;
              }
            },
          });
          return data;
        } catch (err) {
          console.error(err);
          throw new Error('Invalid response while downloading parquet file');
        }
      } else {
        const blob = await filesDownloadFile(workspace!, name, path);
        if (!blob) throw new Error('Invalid response while downloading file');

        // Handle range requests for non-parquet files
        if (range) {
          const slicedBlob = blob.slice(range[0], range[1]);
          return slicedBlob.text();
        }

        return blob.text();
      }
    },
  });

export const useDatasetFileContent = ({
  workspace,
  name,
  path,
  range,
  ...options
}: UseDatasetFilesOptions) => {
  return useQuery({
    ...datasetFileContentQueryOptions({ workspace, name, path, range }),
    enabled: Boolean(workspace && name && path),
    ...options,
  });
};

export const useDatasetFileContentSuspense = ({
  workspace,
  name,
  path,
  range,
  ...options
}: UseDatasetFilesOptions) => {
  return useSuspenseQuery({
    ...datasetFileContentQueryOptions({ workspace, name, path, range }),
    ...options,
  });
};
