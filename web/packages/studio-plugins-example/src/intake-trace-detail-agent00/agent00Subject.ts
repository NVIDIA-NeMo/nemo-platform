// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Span, Trace } from '@nemo/sdk/generated/platform/schema';

/** Primary label for agent00 trace/span accordions (e.g. `_on_task_setup`). */
export const getAgent00SpanSubject = (span: Span): string =>
  span.name || span.tool_name || span.model || span.agent_name || span.span_id;

/** Primary label for agent00 trace pages when a trace name exists. */
export const getAgent00TraceSubject = (trace: Trace): string => trace.name || trace.id;

const COLLAPSED_INPUT_PREVIEW_MAX_LENGTH = 70;

/** First input line for collapsed accordion headers, truncated to 70 characters. */
export const getCollapsedInputPreview = (
  input: string | null | undefined,
  maxLength = COLLAPSED_INPUT_PREVIEW_MAX_LENGTH
): string | undefined => {
  const firstLine = input?.trim().split(/\r?\n/, 1)[0]?.trim();
  if (!firstLine) {
    return undefined;
  }
  if (firstLine.length <= maxLength) {
    return firstLine;
  }
  return `${firstLine.slice(0, maxLength)}…`;
};
