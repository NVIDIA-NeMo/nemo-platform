// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { customFetch } from '@nemo/sdk/generated/fetchers/platform';
import { filesDownloadFile, getFilesDownloadFileQueryKey } from '@nemo/sdk/generated/platform/api';
import type { EntityIdentifier } from '@studio/api/common/types';
import { getDatasetFileContentQueryKey } from '@studio/api/datasets/invalidateDatasetCaches';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { isBinaryExtension } from '@studio/util/binaryFile';
import { logger } from '@studio/util/logger';
import { queryOptions, useQuery, UseQueryOptions, useSuspenseQuery } from '@tanstack/react-query';
import axios from 'axios';
import { parquetRead } from 'hyparquet';

/** Parquet INT64 (and similar) columns decode as BigInt; JSON.stringify rejects those by default. */
function jsonReplacer(_key: string, value: unknown): unknown {
  return typeof value === 'bigint' ? value.toString() : value;
}

function serializeParquetRow(row: unknown): string {
  return JSON.stringify(row, jsonReplacer);
}
// Cap text-file preview at 512 KB. Enough to show meaningful JSONL content
// while preventing OOM crashes on multi-GB external dataset shards.
const FILE_PREVIEW_MAX_BYTES = 512 * 1024;

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
      if (isBinaryExtension(path)) {
        throw new Error('Text preview not available for binary files.');
      }

      const [fileUrl] = getFilesDownloadFileQueryKey(
        encodeURIComponent(workspace!),
        encodeURIComponent(name),
        encodeURIComponent(path)
      );

      // HEAD the file to confirm it exists and read Content-Length for conditional ranging.
      // Prepend PLATFORM_BASE_URL so axios resolves the correct host (the relative
      // path alone resolves against window.location, which differs in tests and
      // may differ in deployed environments with a custom base path).
      let fileSize: number | null = null;
      try {
        const headResponse = await axios.head(`${PLATFORM_BASE_URL}${fileUrl}`);
        const contentLength = headResponse.headers['content-length'];
        fileSize = contentLength ? parseInt(String(contentLength), 10) : null;
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
                data += `${serializeParquetRow(row)}\n`;
              }
            },
          });
          return data;
        } catch (err) {
          logger.error('Invalid response while downloading parquet file', err);
          throw new Error('Invalid response while downloading parquet file');
        }
      } else {
        const start = range ? range[0] : 0;
        const end = range ? range[1] : FILE_PREVIEW_MAX_BYTES - 1;
        const needsRange =
          range !== undefined || (fileSize !== null && fileSize > FILE_PREVIEW_MAX_BYTES);
        const blob = await customFetch<Blob>({
          url: fileUrl,
          method: 'GET',
          responseType: 'blob',
          ...(needsRange ? { headers: { Range: `bytes=${start}-${end}` } } : {}),
        });
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
