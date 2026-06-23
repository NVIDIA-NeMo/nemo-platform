// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** Types for the local `experiment-error-*` query plugins (owned by the example package). */

export interface ErrorTypeCount {
  error_type: string;
  count: number;
}

export interface ExperimentErrorSummary {
  total_error_spans: number;
  rows: ErrorTypeCount[];
}

export interface ErrorSpan {
  span_id: string;
  trace_id: string;
  session_id?: string | null;
  name?: string | null;
  error_type: string;
  error_message?: string | null;
  status?: string | null;
  start_time?: string | null;
}

export interface ExperimentErrorSpans {
  total: number;
  spans: ErrorSpan[];
}
