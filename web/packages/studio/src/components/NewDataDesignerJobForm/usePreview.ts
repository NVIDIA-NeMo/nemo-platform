// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DataDesignerConfig } from '@nemo/sdk/generated/data-designer/schema';
import { isAbortError, streamPreview } from '@studio/components/NewDataDesignerJobForm/previewApi';
import { getErrorMessage } from '@studio/components/NewDataDesignerJobForm/utils';
import { useCallback, useRef, useState } from 'react';

const PREVIEW_PATH_TEMPLATE = '/apis/data-designer/v2/workspaces/:workspace/preview';

function buildPreviewPath(workspace: string): string {
  return PREVIEW_PATH_TEMPLATE.replace(':workspace', encodeURIComponent(workspace));
}

export interface UsePreviewOptions {
  workspace: string;
  accessToken: string | undefined;
  getCurrentConfig: () => DataDesignerConfig | undefined;
}

export interface UsePreviewResult {
  previewLogs: string;
  isPreviewing: boolean;
  runPreview: () => Promise<void>;
}

/**
 * Encapsulates preview state and streaming: runs the data designer preview endpoint
 * and appends log lines to previewLogs. Supports abort on re-run.
 */
export function usePreview({
  workspace,
  accessToken,
  getCurrentConfig,
}: UsePreviewOptions): UsePreviewResult {
  const [previewLogs, setPreviewLogs] = useState('');
  const [isPreviewing, setIsPreviewing] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const appendLogLine = useCallback((line: string) => {
    setPreviewLogs((prev) => (prev ? `${prev}\n${line}` : line));
  }, []);

  const runPreview = useCallback(async () => {
    let config: DataDesignerConfig | undefined;
    try {
      config = getCurrentConfig();
    } catch (err) {
      setPreviewLogs(getErrorMessage(err, 'Could not build a preview config from the recipe.'));
      return;
    }
    if (!config) {
      setPreviewLogs('Generate a job spec first, then run Preview.');
      return;
    }

    setPreviewLogs('');
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    const signal = abortRef.current.signal;
    setIsPreviewing(true);

    try {
      await streamPreview(
        buildPreviewPath(workspace),
        { config, num_records: 10 },
        accessToken,
        signal,
        appendLogLine
      );
    } catch (err) {
      if (isAbortError(err)) return;
      appendLogLine(getErrorMessage(err, 'Preview request failed.'));
    } finally {
      setIsPreviewing(false);
      abortRef.current = null;
    }
  }, [workspace, accessToken, getCurrentConfig, appendLogLine]);

  return { previewLogs, isPreviewing, runPreview };
}
