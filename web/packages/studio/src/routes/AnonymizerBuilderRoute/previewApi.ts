// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { PreviewRequest } from '@nemo/sdk/generated/anonymizer/schema';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { asRecord } from '@studio/util/guards';

export type PreviewLogLevel = 'debug' | 'info' | 'warning' | 'error';

export type PreviewFrame =
  | { kind: 'log'; level: PreviewLogLevel; message: string }
  | { kind: 'preview_dataset'; records: Record<string, unknown>[] }
  | { kind: 'trace_dataset'; records: Record<string, unknown>[]; originalTextColumn?: string }
  | { kind: 'failed_records'; records: Record<string, unknown>[] }
  | { kind: 'heartbeat' }
  | { kind: 'done' }
  | { kind: 'error'; message: string };

const LOG_LEVELS: readonly string[] = ['debug', 'info', 'warning', 'error'];

const asRecordList = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value)
    ? value.flatMap((entry) => {
        const row = asRecord(entry);
        return row ? [row] : [];
      })
    : [];

/** Frames arrive as NDJSON. Anything unrecognised is dropped rather than surfaced as an error. */
export const parsePreviewFrame = (line: string): PreviewFrame | undefined => {
  const trimmed = line.trim();
  if (!trimmed) return undefined;

  let decoded: unknown;
  try {
    decoded = JSON.parse(trimmed);
  } catch {
    return undefined;
  }

  const frame = asRecord(decoded);
  const kind = frame?.kind;
  if (!frame || typeof kind !== 'string') return undefined;

  switch (kind) {
    case 'log': {
      const { level, message } = frame;
      return {
        kind,
        level: LOG_LEVELS.includes(String(level)) ? (level as PreviewLogLevel) : 'info',
        message: typeof message === 'string' ? message : '',
      };
    }
    case 'preview_dataset':
    case 'failed_records':
      return { kind, records: asRecordList(frame.records) };
    case 'trace_dataset': {
      const column = frame.original_text_column;
      return {
        kind,
        records: asRecordList(frame.records),
        originalTextColumn: typeof column === 'string' ? column : undefined,
      };
    }
    case 'heartbeat':
    case 'done':
      return { kind };
    case 'error':
      return {
        kind,
        message: typeof frame.message === 'string' ? frame.message : 'The preview run failed.',
      };
    default:
      return undefined;
  }
};

/** FastAPI returns `detail` as either a plain string or a list of pydantic errors. */
const messageFromErrorBody = (body: string): string | undefined => {
  let decoded: unknown;
  try {
    decoded = JSON.parse(body);
  } catch {
    return body.trim() || undefined;
  }
  const detail = asRecord(decoded)?.detail;
  if (typeof detail === 'string') return detail;
  if (!Array.isArray(detail)) return undefined;
  const messages = detail.flatMap((item) => {
    const msg = asRecord(item)?.msg;
    return typeof msg === 'string' ? [msg] : [];
  });
  return messages.length ? messages.join(' ') : undefined;
};

export const isAbortError = (error: unknown): boolean =>
  error instanceof DOMException ? error.name === 'AbortError' : false;

const previewPath = (workspace: string): string =>
  `/apis/anonymizer/v2/workspaces/${encodeURIComponent(workspace)}/preview`;

export const streamAnonymizerPreview = async (
  workspace: string,
  request: PreviewRequest,
  accessToken: string | undefined,
  signal: AbortSignal,
  onFrame: (frame: PreviewFrame) => void
): Promise<void> => {
  const response = await fetch(`${PLATFORM_BASE_URL}${previewPath(workspace)}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      'X-Source': 'NeMo Studio',
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(messageFromErrorBody(body) ?? `Preview failed: ${response.status}`);
  }
  if (!response.body) throw new Error('The preview response was empty.');

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';

  const emit = (line: string) => {
    const frame = parsePreviewFrame(line);
    if (frame) onFrame(frame);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += value;
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    lines.forEach(emit);
  }
  emit(buffer);
};
