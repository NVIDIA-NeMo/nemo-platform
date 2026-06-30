// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Span } from '@nemo/sdk/generated/platform/schema';
import {
  buildSpanLlmEntries,
  buildSpanSummaryEntries,
  mergeSpanDetails,
} from '@studio/components/IntakeDetail/IntakeComponents/spanKeyValues';
import { mockSpanById } from '@studio/mocks/intake/telemetry';
import { EMPTY_VALUE } from '@studio/util/intakeTelemetry';

describe('spanKeyValues', () => {
  it('builds span summary entries without crashing on empty object fields', () => {
    const span = mockSpanById('span-llm-001');
    expect(span).toBeDefined();

    const entries = buildSpanSummaryEntries(
      {
        ...span!,
        usage_details: {},
        cost_details: {},
        evaluation_context: { metadata: {} },
      },
      { workspace: 'default' }
    );

    expect(entries.every((entry) => typeof entry.value === 'string' || entry.value != null)).toBe(
      true
    );
    expect(entries.map((entry) => entry.label)).not.toEqual(
      expect.arrayContaining(['Usage Details', 'Cost Details', 'Model', 'Provider'])
    );
  });

  it('puts usage details in the LLM accordion entries', () => {
    const span: Span = {
      span_id: 'span-test-001',
      session_id: 'session-001',
      workspace: 'default',
      kind: 'LLM',
      source: 'otel',
      started_at: '2026-05-20T16:42:08Z',
      status: 'success',
      ingested_at: '2026-05-20T16:42:15Z',
      usage_details: { audio_tokens: 12 },
    };

    const entries = buildSpanLlmEntries(span);
    const usageEntry = entries.find((entry) => entry.id === 'usage_details');

    expect(usageEntry?.value).toBe(JSON.stringify({ audio_tokens: 12 }, null, 2));
    expect(
      buildSpanSummaryEntries(span, { workspace: 'default' }).map((entry) => entry.id)
    ).not.toContain('usage_details');
  });

  it('builds LLM accordion entries for model, token, and cost fields', () => {
    const span = mockSpanById('span-llm-001');
    expect(span).toBeDefined();

    const entries = buildSpanLlmEntries(span!);

    expect(entries.length).toBeGreaterThan(0);
    expect(entries.map((entry) => entry.label)).toEqual(
      expect.arrayContaining(['Model', 'Provider', 'Input Tokens', 'Total Cost'])
    );
  });

  it('always shows core LLM metrics with placeholders when values are absent', () => {
    const span: Span = {
      span_id: 'span-tool-001',
      session_id: 'session-001',
      workspace: 'default',
      kind: 'TOOL',
      source: 'otel',
      started_at: '2026-05-20T16:42:08Z',
      status: 'success',
      ingested_at: '2026-05-20T16:42:15Z',
      tool_name: 'lookup',
    };

    const entries = buildSpanLlmEntries(span);

    expect(entries.map((entry) => entry.label)).toEqual(
      expect.arrayContaining(['Model', 'Provider', 'Input Tokens', 'Total Cost'])
    );
    expect(entries.find((entry) => entry.id === 'model')?.value).toBe(EMPTY_VALUE);
  });

  it('backfills LLM metrics from the list span when detail fetch omits them', () => {
    const summarySpan = mockSpanById('span-llm-001');
    expect(summarySpan).toBeDefined();

    const detailSpan: Span = {
      span_id: summarySpan!.span_id,
      session_id: summarySpan!.session_id,
      workspace: summarySpan!.workspace,
      kind: summarySpan!.kind,
      source: summarySpan!.source,
      started_at: summarySpan!.started_at,
      ended_at: summarySpan!.ended_at,
      status: summarySpan!.status,
      ingested_at: summarySpan!.ingested_at,
      input: summarySpan!.input,
      output: summarySpan!.output,
    };

    const merged = mergeSpanDetails(summarySpan, detailSpan);
    const entries = buildSpanLlmEntries(merged);

    expect(entries.find((entry) => entry.id === 'model')?.value).toBe(summarySpan!.model);
    expect(entries.find((entry) => entry.id === 'input_tokens')?.value).toBe('1,240');
  });

  it('includes kind in span summary but omits status/timing rendered in the template view', () => {
    const span = mockSpanById('span-llm-001');
    expect(span).toBeDefined();

    const labels = buildSpanSummaryEntries(span!, { workspace: 'default' }).map(
      (entry) => entry.label
    );

    expect(labels).toEqual(expect.arrayContaining(['Kind']));
    // Status, Started, and Ended lead every template's key/value header, so the
    // Metadata section omits them to avoid duplication.
    expect(labels).not.toEqual(
      expect.arrayContaining(['Status', 'Started', 'Ended', 'Model', 'Provider', 'Total Cost'])
    );
  });
});
