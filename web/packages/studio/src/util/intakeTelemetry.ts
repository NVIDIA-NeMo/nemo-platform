// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Span, SpanEvaluationContext, Trace } from '@nemo/sdk/generated/platform/schema';

export const EMPTY_VALUE = '—';

export type SpanTableRow = Span & {
  hierarchyDepth: number;
  hierarchyStatus?: 'parent_outside_page' | 'cycle_or_unreachable';
};

export const formatInteger = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return EMPTY_VALUE;
  return value.toLocaleString();
};

export const formatCost = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return EMPTY_VALUE;
  if (value === 0) return '$0.00';
  if (Math.abs(value) < 0.01) {
    return `$${value.toFixed(6).replace(/0+$/, '').replace(/\.$/, '')}`;
  }
  return `$${value.toFixed(2)}`;
};

export const formatDurationMs = (value: number | null | undefined): string => {
  if (value === null || value === undefined) return EMPTY_VALUE;
  if (value < 1) return `${value.toFixed(2)} ms`;
  if (value < 1000) return `${Math.round(value).toLocaleString()} ms`;
  if (value < 60_000) return `${(value / 1000).toFixed(2)} s`;
  return `${(value / 60_000).toFixed(2)} min`;
};

export const getSpanDurationMs = (span: Span): number | undefined => {
  if (!span.ended_at) return undefined;
  const startedAt = Date.parse(span.started_at);
  const endedAt = Date.parse(span.ended_at);
  if (Number.isNaN(startedAt) || Number.isNaN(endedAt)) return undefined;
  return Math.max(endedAt - startedAt, 0);
};

export const getTraceDisplayName = (trace: Trace): string => {
  return trace.name || trace.id;
};

export const getSpanDisplayName = (span: Span): string => {
  return span.name || span.tool_name || span.model || span.agent_name || span.kind;
};

export const getSpanSubject = (span: Span): string => {
  return (
    span.tool_name || span.model || span.agent_name || span.provider || span.project || span.kind
  );
};

export const formatMaybe = (value: string | number | boolean | null | undefined): string => {
  if (value === null || value === undefined || value === '') return EMPTY_VALUE;
  if (typeof value === 'number') return formatInteger(value);
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return value;
};

export const getEvaluationContextSummary = (
  context: SpanEvaluationContext | null | undefined
): string => {
  if (!context) return EMPTY_VALUE;
  return context.evaluation_run_id || context.evaluation_id || context.test_case_id || EMPTY_VALUE;
};

export const hasEvaluationContext = (context: SpanEvaluationContext | null | undefined): boolean =>
  Boolean(
    context &&
    (context.evaluation_id ||
      context.evaluation_sha ||
      context.evaluation_run_id ||
      context.test_case_id ||
      (context.metadata && Object.keys(context.metadata).length > 0))
  );

export const compareSpansByStartedAt = (a: Span, b: Span): number => {
  const aStartedAt = Date.parse(a.started_at);
  const bStartedAt = Date.parse(b.started_at);
  if (Number.isNaN(aStartedAt) || Number.isNaN(bStartedAt) || aStartedAt === bStartedAt) {
    return a.span_id.localeCompare(b.span_id);
  }
  return aStartedAt - bStartedAt;
};

export const buildSpanHierarchyRows = (spans: Span[]): SpanTableRow[] => {
  const spansById = new Map(spans.map((span) => [span.span_id, span]));
  const childrenByParent = new Map<string, Span[]>();
  const roots: Span[] = [];
  const orphans: Span[] = [];

  for (const span of spans) {
    if (span.parent_span_id && spansById.has(span.parent_span_id)) {
      const children = childrenByParent.get(span.parent_span_id) ?? [];
      children.push(span);
      childrenByParent.set(span.parent_span_id, children);
    } else if (span.parent_span_id) {
      orphans.push(span);
    } else {
      roots.push(span);
    }
  }

  for (const children of childrenByParent.values()) {
    children.sort(compareSpansByStartedAt);
  }
  roots.sort(compareSpansByStartedAt);
  orphans.sort(compareSpansByStartedAt);

  const rows: SpanTableRow[] = [];
  const visited = new Set<string>();

  const collect = (
    span: Span,
    depth: number,
    hierarchyStatus?: SpanTableRow['hierarchyStatus']
  ): void => {
    if (visited.has(span.span_id)) return;
    visited.add(span.span_id);
    rows.push({ ...span, hierarchyDepth: depth, hierarchyStatus });
    for (const child of childrenByParent.get(span.span_id) ?? []) {
      collect(child, depth + 1);
    }
  };

  for (const root of roots) {
    collect(root, 0);
  }

  for (const orphan of orphans) {
    collect(orphan, 0, 'parent_outside_page');
  }

  for (const span of spans) {
    collect(span, 0, 'cycle_or_unreachable');
  }

  return rows;
};
