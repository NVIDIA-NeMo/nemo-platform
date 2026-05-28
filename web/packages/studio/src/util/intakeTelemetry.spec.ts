// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SpanKind, SpanStatus, type Span } from '@nemo/sdk/generated/platform/schema';
import {
  buildSpanHierarchyRows,
  compareSpansByStartedAt,
  formatCost,
} from '@studio/util/intakeTelemetry';

const makeSpan = (span: Partial<Span> & Pick<Span, 'span_id' | 'started_at'>): Span => ({
  session_id: 'session-1',
  workspace: 'default',
  kind: SpanKind.AGENT,
  source: 'otel',
  status: SpanStatus.success,
  ingested_at: '2026-05-20T00:00:00Z',
  ...span,
});

describe('intakeTelemetry span hierarchy helpers', () => {
  it('formats sub-cent costs without trailing zero padding', () => {
    expect(formatCost(0.0032)).toBe('$0.0032');
  });

  it('sorts spans by started_at and falls back to span_id', () => {
    const a = makeSpan({ span_id: 'span-b', started_at: '2026-05-20T00:00:00Z' });
    const b = makeSpan({ span_id: 'span-a', started_at: '2026-05-20T00:00:00Z' });
    const c = makeSpan({ span_id: 'span-c', started_at: '2026-05-20T00:00:01Z' });

    expect([c, a, b].sort(compareSpansByStartedAt).map((span) => span.span_id)).toEqual([
      'span-a',
      'span-b',
      'span-c',
    ]);
  });

  it('builds nested rows by parent_span_id', () => {
    const rows = buildSpanHierarchyRows([
      makeSpan({
        span_id: 'child-2',
        parent_span_id: 'root',
        started_at: '2026-05-20T00:00:03Z',
      }),
      makeSpan({ span_id: 'root', started_at: '2026-05-20T00:00:01Z' }),
      makeSpan({
        span_id: 'grandchild',
        parent_span_id: 'child-1',
        started_at: '2026-05-20T00:00:04Z',
      }),
      makeSpan({
        span_id: 'child-1',
        parent_span_id: 'root',
        started_at: '2026-05-20T00:00:02Z',
      }),
    ]);

    expect(rows.map((row) => [row.span_id, row.hierarchyDepth])).toEqual([
      ['root', 0],
      ['child-1', 1],
      ['grandchild', 2],
      ['child-2', 1],
    ]);
  });

  it('keeps multiple roots ordered by start time', () => {
    const rows = buildSpanHierarchyRows([
      makeSpan({ span_id: 'root-2', started_at: '2026-05-20T00:00:03Z' }),
      makeSpan({ span_id: 'root-1', started_at: '2026-05-20T00:00:01Z' }),
      makeSpan({
        span_id: 'child-1',
        parent_span_id: 'root-1',
        started_at: '2026-05-20T00:00:02Z',
      }),
    ]);

    expect(rows.map((row) => [row.span_id, row.hierarchyDepth])).toEqual([
      ['root-1', 0],
      ['child-1', 1],
      ['root-2', 0],
    ]);
  });

  it('keeps spans visible when their parent is not in the current page', () => {
    const rows = buildSpanHierarchyRows([
      makeSpan({
        span_id: 'orphan-child',
        parent_span_id: 'missing-parent',
        started_at: '2026-05-20T00:00:01Z',
      }),
    ]);

    expect(rows.map((row) => [row.span_id, row.hierarchyDepth, row.hierarchyStatus])).toEqual([
      ['orphan-child', 0, 'parent_outside_page'],
    ]);
  });

  it('keeps cyclic spans visible with an unresolved hierarchy marker', () => {
    const rows = buildSpanHierarchyRows([
      makeSpan({
        span_id: 'span-1',
        parent_span_id: 'span-2',
        started_at: '2026-05-20T00:00:01Z',
      }),
      makeSpan({
        span_id: 'span-2',
        parent_span_id: 'span-1',
        started_at: '2026-05-20T00:00:02Z',
      }),
    ]);

    expect(rows.map((row) => [row.span_id, row.hierarchyDepth, row.hierarchyStatus])).toEqual([
      ['span-1', 0, 'cycle_or_unreachable'],
      ['span-2', 1, undefined],
    ]);
  });
});
