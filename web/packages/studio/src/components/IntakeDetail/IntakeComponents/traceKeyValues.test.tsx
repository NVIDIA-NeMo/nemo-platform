// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  buildEvaluationContextEntries,
  buildSessionHighlightMetrics,
  buildTraceSummaryEntries,
} from '@studio/components/IntakeDetail/IntakeComponents/traceKeyValues';
import { mockSessionById, mockTraceById } from '@studio/mocks/intake/telemetry';

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

  it('builds session headline metrics without a trace error count', () => {
    const session = mockSessionById('session-agent-run-001');
    expect(session).toBeDefined();

    const metrics = buildSessionHighlightMetrics(session!);

    expect(metrics.map(({ id }) => id)).toEqual([
      'span_count',
      'duration_ms',
      'total_tokens',
      'cost_usd',
    ]);
  });

  it('includes evaluation context entries when present', () => {
    const trace = mockTraceById('trace-agent-run-001');
    expect(trace).toBeDefined();

    const entries = buildEvaluationContextEntries(trace!.evaluation_context);

    expect(entries.map((entry) => entry.label)).toEqual(['Evaluation ID', 'Test Case ID']);
  });

  it('returns no evaluation context entries when context is absent', () => {
    const trace = mockTraceById('trace-agent-run-002');
    expect(trace).toBeDefined();

    expect(buildEvaluationContextEntries(trace!.evaluation_context)).toEqual([]);
  });
});
