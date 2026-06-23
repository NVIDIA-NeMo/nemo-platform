// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  isQueryPluginResult,
  normalizeQueryPluginResult,
} from '@nemo/studio-plugins-example/queryPlugin/useQueryPlugin';
import { describe, expect, it } from 'vitest';

describe('normalizeQueryPluginResult', () => {
  it('passes through generic API wrapper responses', () => {
    const wrapped = {
      query_plugin_id: 'experiment-error-summary',
      data: { total_error_spans: 3, rows: [] },
    };
    expect(normalizeQueryPluginResult('experiment-error-summary', wrapped)).toEqual(wrapped);
  });

  it('wraps legacy flat plugin output', () => {
    const flat = { total_error_spans: 72, rows: [{ error_type: 'RateLimitError', count: 24 }] };
    expect(normalizeQueryPluginResult('experiment-error-summary', flat)).toEqual({
      query_plugin_id: 'experiment-error-summary',
      data: flat,
    });
  });

  it('detects wrapped vs flat payloads', () => {
    expect(isQueryPluginResult({ query_plugin_id: 'x', data: {} })).toBe(true);
    expect(isQueryPluginResult({ total_error_spans: 1, rows: [] })).toBe(false);
  });
});
