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
// while preventing OOM crashes on multi-GB external dataset shards. Text files larger
// than this are fetched with a Range request, so callers that write content back must not
// overwrite the source (the loaded rows are only a prefix of the file).
export const FILE_PREVIEW_MAX_BYTES = 512 * 1024;

export const EDITOR_MAX_BYTES = 8 * 1024 * 1024;

interface UseDatasetFileContentParams extends Required<EntityIdentifier> {
  path: string;
  range?: [number, number];
  /**
   * Load the entire file (no preview cap) so its content can be safely edited and written
   * back. Refuses files larger than {@link EDITOR_MAX_BYTES}. Ignored when `range` is set.
   * @defaultValue false — callers get the size-capped preview.
   */
  fullContent?: boolean;
}

export type UseDatasetFilesOptions = Omit<UseQueryOptions<string, Error>, 'queryFn' | 'queryKey'> &
  UseDatasetFileContentParams;

export const datasetFileContentQueryOptions = ({
  workspace,
  name,
  path,
  range,
  fullContent,
}: UseDatasetFileContentParams) =>
  queryOptions<string, Error>({
    staleTime: Infinity, // We should prevent refetching full files (costly) unless directly invalidated
    queryKey: [
      ...getDatasetFileContentQueryKey(workspace!, name, path),
      ...(range ? range.map((bound) => String(bound)) : []),
      ...(fullContent ? ['full'] : []),
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

      // Enforce the editor cap before either branch pulls the whole file into memory —
      // the parquet branch downloads the entire blob unconditionally, so a check inside
      // it would come after the very download it's meant to prevent. Fail closed when the
      // size is unknown: a missing or non-numeric Content-Length must not slip an
      // unbounded file through.
      if (fullContent && range === undefined) {
        if (fileSize === null || Number.isNaN(fileSize) || fileSize > EDITOR_MAX_BYTES) {
          throw new Error('File is too large to edit in the browser.');
        }
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
        const isSizeCappedPreview =
          !fullContent &&
          range === undefined &&
          fileSize !== null &&
          fileSize > FILE_PREVIEW_MAX_BYTES;
        const needsRange = range !== undefined || isSizeCappedPreview;
        const blob = await customFetch<Blob>({
          url: fileUrl,
          method: 'GET',
          responseType: 'blob',
          ...(needsRange ? { headers: { Range: `bytes=${start}-${end}` } } : {}),
        });
        const text = await blob.text();
        if (isSizeCappedPreview) {
          const lastNewline = text.lastIndexOf('\n');
          return lastNewline >= 0 ? text.slice(0, lastNewline + 1) : text;
        }
        return text;
      }
    },
  });

export const useDatasetFileContent = ({
  workspace,
  name,
  path,
  range,
  fullContent,
  ...options
}: UseDatasetFilesOptions) => {
  return useQuery({
    ...datasetFileContentQueryOptions({ workspace, name, path, range, fullContent }),
    enabled: Boolean(workspace && name && path),
    ...options,
  });
};

export const useDatasetFileContentSuspense = ({
  workspace,
  name,
  path,
  range,
  fullContent,
  ...options
}: UseDatasetFilesOptions) => {
  return useSuspenseQuery({
    ...datasetFileContentQueryOptions({ workspace, name, path, range, fullContent }),
    ...options,
  });
};
