// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { PreviewRequest } from '@nemo/sdk/generated/anonymizer/schema';
import {
  isAbortError,
  streamAnonymizerPreview,
  type PreviewFrame,
} from '@studio/routes/AnonymizerBuilderRoute/previewApi';
import { startTransition, useCallback, useEffect, useRef, useState } from 'react';

const DEFAULT_TEXT_COLUMN = 'text';

interface PreviewResult {
  readonly records: Record<string, unknown>[];
  readonly textColumn: string;
  readonly failedRecords: Record<string, unknown>[];
}

const EMPTY_RESULT: PreviewResult = {
  records: [],
  textColumn: DEFAULT_TEXT_COLUMN,
  failedRecords: [],
};

export interface UseAnonymizerPreviewOptions {
  readonly workspace: string;
  readonly accessToken: string | undefined;
  /** Returns the request to preview, or undefined when the form isn't ready. */
  readonly getRequest: () => Promise<PreviewRequest | undefined>;
}

export interface UseAnonymizerPreview {
  readonly result: PreviewResult;
  readonly logs: readonly string[];
  readonly isPreviewing: boolean;
  readonly error: string | undefined;
  readonly hasRun: boolean;
  readonly wasStopped: boolean;
  readonly runPreview: () => Promise<void>;
  /** The server unwinds on disconnect, but an in-flight model call still finishes. */
  readonly stopPreview: () => void;
}

export const useAnonymizerPreview = ({
  workspace,
  accessToken,
  getRequest,
}: UseAnonymizerPreviewOptions): UseAnonymizerPreview => {
  const [result, setResult] = useState<PreviewResult>(EMPTY_RESULT);
  const [logs, setLogs] = useState<string[]>([]);
  const [isPreviewing, setIsPreviewing] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);
  const [hasRun, setHasRun] = useState(false);
  const [wasStopped, setWasStopped] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const stopPreview = useCallback(() => {
    if (!abortRef.current) return;
    setWasStopped(true);
    abortRef.current.abort();
  }, []);

  const runPreview = useCallback(async () => {
    const request = await getRequest();
    if (!request) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setResult(EMPTY_RESULT);
    setLogs([]);
    setError(undefined);
    setHasRun(true);
    setWasStopped(false);
    setIsPreviewing(true);

    const onFrame = (frame: PreviewFrame) => {
      switch (frame.kind) {
        case 'log':
          // One frame per read is too far apart for React to batch; keeps Stop responsive.
          startTransition(() => setLogs((prev) => [...prev, frame.message]));
          break;
        case 'trace_dataset':
          setResult((prev) => ({
            ...prev,
            records: frame.records,
            textColumn: frame.originalTextColumn ?? prev.textColumn,
          }));
          break;
        case 'failed_records':
          setResult((prev) => ({ ...prev, failedRecords: frame.records }));
          break;
        case 'error':
          setError(frame.message);
          break;
        default:
          break;
      }
    };

    try {
      await streamAnonymizerPreview(workspace, request, accessToken, controller.signal, onFrame);
    } catch (err) {
      if (isAbortError(err)) return;
      setError((err instanceof Error && err.message) || 'The preview run failed.');
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setIsPreviewing(false);
      }
    }
  }, [workspace, accessToken, getRequest]);

  return { result, logs, isPreviewing, error, hasRun, wasStopped, runPreview, stopPreview };
};
