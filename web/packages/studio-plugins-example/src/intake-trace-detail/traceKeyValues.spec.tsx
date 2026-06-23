// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { mockTraceById } from '@studio/mocks/intake/telemetry';
import {
  buildExperimentContextEntries,
  buildTraceHighlightMetrics,
  buildTraceSummaryEntries,
} from '@nemo/studio-plugins-example/intake-trace-detail/traceKeyValues';

describe('traceKeyValues', () => {
  it('builds trace summary entries without headline metrics', () => {
    const trace = mockTraceById('trace-agent-run-001');
    expect(trace).toBeDefined();

    const entries = buildTraceSummaryEntries(trace!, { workspace: 'default' });
    const labels = entries.map((entry) => entry.label);

    expect(labels).toEqual(expect.arrayContaining(['Started', 'Trace ID', 'Root Span']));
    expect(labels).not.toEqual(expect.arrayContaining(['Spans', 'Duration', 'Status', 'Total Cost', 'Total Tokens']));
  });

  it('builds headline metrics for the top metrics card', () => {
    const trace = mockTraceById('trace-agent-run-001');
    expect(trace).toBeDefined();

    const metrics = buildTraceHighlightMetrics(trace!);

    expect(metrics).toEqual([
      { id: 'span_count', label: 'Spans', value: '4' },
      { id: 'error_count', label: 'Errors', value: '0' },
      { id: 'duration_ms', label: 'Duration', value: '12.23 s' },
      { id: 'cost_usd', label: 'Total Cost', value: '$0.0032' },
      { id: 'input_tokens', label: 'Input Tokens', value: '1,240' },
      { id: 'output_tokens', label: 'Output Tokens', value: '386' },
      { id: 'total_tokens', label: 'Total Tokens', value: '1,754' },
    ]);
  });

  it('includes experiment context entries when present', () => {
    const trace = mockTraceById('trace-agent-run-001');
    expect(trace).toBeDefined();

    const entries = buildExperimentContextEntries(trace!.experiment_context);

    expect(entries.map((entry) => entry.label)).toEqual(['Experiment ID', 'Test Case ID']);
  });

  it('returns no experiment context entries when context is absent', () => {
    const trace = mockTraceById('trace-agent-run-002');
    expect(trace).toBeDefined();

    expect(buildExperimentContextEntries(trace!.experiment_context)).toEqual([]);
  });
});
