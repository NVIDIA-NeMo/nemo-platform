// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { filesDownloadFile, filesHeadFile } from '@nemo/sdk/generated/platform/api';
import { EntityIdentifier } from '@studio/api/common/types';
import { getDatasetFileContentQueryKey } from '@studio/api/datasets/invalidateDatasetCaches';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { isBinaryExtension } from '@studio/util/binaryFile';
import { queryOptions, useQuery, UseQueryOptions, useSuspenseQuery } from '@tanstack/react-query';
import { parquetRead } from 'hyparquet';
import { useAuth } from 'react-oidc-context';

// Cap text-file preview at 512 KB. Enough to show meaningful JSONL content
// while preventing OOM crashes on multi-GB external dataset shards.
const FILE_PREVIEW_MAX_BYTES = 512 * 1024;

interface UseDatasetFileContentParams extends Required<EntityIdentifier> {
  path: string;
  range?: [number, number];
  accessToken?: string;
}

export type UseDatasetFilesOptions = Omit<UseQueryOptions<string, Error>, 'queryFn' | 'queryKey'> &
  UseDatasetFileContentParams;

export const datasetFileContentQueryOptions = ({
  workspace,
  name,
  path,
  range,
  accessToken,
}: UseDatasetFileContentParams) =>
  queryOptions<string, Error>({
    staleTime: Infinity, // We should prevent refetching full files (costly) unless directly invalidated
    queryKey: [
      ...getDatasetFileContentQueryKey(workspace!, name, path),
      ...(range ? range.map((bound) => String(bound)) : []),
    ],
    queryFn: async () => {
      if (isBinaryExtension(path)) {
        throw new Error('Text preview not available for binary files.');
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
        const end = range ? range[1] : FILE_PREVIEW_MAX_BYTES - 1;
        const start = range ? range[0] : 0;
        const fileUrl = [
          PLATFORM_BASE_URL,
          '/apis/files/v2/workspaces/',
          encodeURIComponent(workspace!),
          '/filesets/',
          encodeURIComponent(name),
          '/-/',
          encodeURIComponent(path),
        ].join('');
        const headers: Record<string, string> = {
          Range: `bytes=${start}-${end}`,
        };
        if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
        const res = await fetch(fileUrl, { headers });
        if (!res.ok && res.status !== 206)
          throw new Error('Invalid response while downloading file');
        return res.text();
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
  const auth = useAuth();
  const accessToken = auth.user?.access_token;
  return useQuery({
    ...datasetFileContentQueryOptions({ workspace, name, path, range, accessToken }),
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
