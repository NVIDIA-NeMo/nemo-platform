// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { filesDownloadFile } from '@nemo/sdk/generated/platform/api';
import { queryOptions } from '@tanstack/react-query';

export interface FileEncodingResult {
  ok: boolean;
}

interface DatasetFileEncodingParams {
  workspace: string;
  name: string;
  path: string;
}

/**
 * Strict UTF-8 validation for a single fileset file.
 *
 * Runs in parallel with `datasetFileContentQueryOptions` (which uses lossy
 * `Blob.text()` decoding for backwards compatibility with non-validation
 * consumers). Customizer's training pipeline opens every file with
 * encoding="utf-8" and Python's default 'strict' error mode, so non-UTF-8
 * input fails the training job with UnicodeDecodeError. We catch that here
 * pre-submit by using `TextDecoder('utf-8', { fatal: true })`, which throws
 * on the same byte sequences Python's strict UTF-8 decoder would reject.
 *
 * Note: this fetches the file a second time alongside the content query.
 * Worth living with for now to keep the blast radius inside the customizer
 * fine-tuning form. Folding the strict decode into
 * `datasetFileContentQueryOptions` itself (and removing this query) is
 * tracked as a follow-up.
 */
export const datasetFileEncodingQueryOptions = ({
  workspace,
  name,
  path,
}: DatasetFileEncodingParams) =>
  queryOptions<FileEncodingResult>({
    staleTime: Infinity,
    queryKey: ['fileset-encoding-utf8', workspace, name, path],
    queryFn: async () => {
      const blob = await filesDownloadFile(workspace, name, path);
      if (!blob) {
        throw new Error('Invalid response while downloading file for encoding check');
      }
      const buffer = await blob.arrayBuffer();
      try {
        new TextDecoder('utf-8', { fatal: true }).decode(buffer);
        return { ok: true };
      } catch {
        // The browser's TextDecoder error string is implementation-specific
        // and not user-friendly ("Failed to execute 'decode' on 'TextDecoder'").
        // Drop it on the floor — the panel only needs to know pass/fail and
        // surfaces the offending file path itself.
        return { ok: false };
      }
    },
  });
