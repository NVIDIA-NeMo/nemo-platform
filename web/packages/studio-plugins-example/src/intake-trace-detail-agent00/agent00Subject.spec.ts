// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { mockSpanById } from '@studio/mocks/intake/telemetry';
import {
  getAgent00SpanSubject,
  getAgent00TraceSubject,
  getCollapsedInputPreview,
} from '@nemo/studio-plugins-example/intake-trace-detail-agent00/agent00Subject';

describe('agent00Subject', () => {
  it('uses span name as the accordion subject', () => {
    const span = mockSpanById('span-llm-001');
    expect(span).toBeDefined();

    expect(getAgent00SpanSubject(span!)).toBe('Generate final response');
  });

  it('falls back through tool and model identifiers', () => {
    expect(
      getAgent00SpanSubject({
        span_id: 'span-1',
        session_id: 'session-1',
        workspace: 'agent00',
        kind: 'TOOL',
        source: 'otel',
        started_at: '2026-05-20T16:42:08Z',
        status: 'success',
        ingested_at: '2026-05-20T16:42:15Z',
        tool_name: '_task_file_mutation_allowed',
      })
    ).toBe('_task_file_mutation_allowed');
  });

  it('uses trace name as the trace subject', () => {
    expect(
      getAgent00TraceSubject({
        id: 'trace-1',
        session_id: 'session-1',
        workspace: 'agent00',
        started_at: '2026-05-20T16:42:00Z',
        status: 'success',
        name: '_on_task_setup',
      })
    ).toBe('_on_task_setup');
  });

  it('truncates the first input line for collapsed accordion headers', () => {
    expect(getCollapsedInputPreview('_on_task_setup()\nignored line')).toBe('_on_task_setup()');
    expect(getCollapsedInputPreview('x'.repeat(80))?.length).toBe(71);
    expect(getCollapsedInputPreview('x'.repeat(80))?.endsWith('…')).toBe(true);
    expect(getCollapsedInputPreview('   \n')).toBeUndefined();
  });
});
