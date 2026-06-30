// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  buildExperimentContextEntries,
  buildTraceHighlightMetrics,
  buildTraceSummaryEntries,
} from '@studio/components/IntakeDetail/IntakeComponents/traceKeyValues';
import { mockTraceById } from '@studio/mocks/intake/telemetry';
import { EMPTY_VALUE } from '@studio/util/intakeTelemetry';

describe('traceKeyValues', () => {
  it('builds trace summary entries without headline metrics', () => {
    const trace = mockTraceById('trace-agent-run-001');
    expect(trace).toBeDefined();

    const entries = buildTraceSummaryEntries(trace!, { workspace: 'default' });
    const labels = entries.map((entry) => entry.label);

    expect(labels).toEqual(expect.arrayContaining(['Name', 'Trace ID', 'Root Span', 'Session ID']));
    // Status/timing and token/cost values are surfaced in the header, not metadata.
    expect(labels).not.toEqual(
      expect.arrayContaining([
        'Started',
        'Ended',
        'Cached Tokens',
        'Input Cost',
        'Output Cost',
        'Spans',
        'Status',
        'Total Cost',
        'Total Tokens',
      ])
    );
  });

  it('builds headline metrics for the top metrics card', () => {
    const trace = mockTraceById('trace-agent-run-001');
    expect(trace).toBeDefined();

    const metrics = buildTraceHighlightMetrics(trace!);

    expect(metrics).toEqual([
      { id: 'span_count', label: 'Spans', value: '4' },
      { id: 'error_count', label: 'Errors', value: '0' },
      { id: 'duration_ms', label: 'Duration', value: '12.23 s' },
      {
        id: 'total_tokens',
        label: 'Total Tokens',
        value: '1,754',
        details: [
          { id: 'input_tokens', label: 'Input Tokens', value: '1,240' },
          { id: 'output_tokens', label: 'Output Tokens', value: '386' },
          { id: 'cached_tokens', label: 'Cached Tokens', value: '128' },
        ],
      },
      {
        id: 'cost_usd',
        label: 'Total Cost',
        value: '$0.0032',
        details: [
          { id: 'cost_input_usd', label: 'Input Cost', value: EMPTY_VALUE },
          { id: 'cost_output_usd', label: 'Output Cost', value: EMPTY_VALUE },
        ],
      },
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
