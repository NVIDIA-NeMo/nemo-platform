// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import type { ExperimentContext, Trace } from '@nemo/sdk/generated/platform/schema';
import { getIntakeSpanRoute } from '@studio/routes/utils';
import {
  EMPTY_VALUE,
  formatCost,
  formatDurationMs,
  formatInteger,
  formatMaybe,
} from '@studio/util/intakeTelemetry';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import type { HighlightMetric, KeyValueEntry } from '@nemo/studio-plugins-example/intake-trace-detail-agent00/keyValueTypes';
import {
  formatUnknownKeyValue,
  isMeaningfulValue,
} from '@nemo/studio-plugins-example/intake-trace-detail-agent00/keyValueFormatting';

interface TraceKeyValueContext {
  workspace: string;
}

type TraceFieldResolver = (trace: Trace, ctx: TraceKeyValueContext) => ReactNode | null | undefined;

interface TraceFieldDescriptor {
  readonly key: keyof Trace | string;
  readonly label: string;
  readonly resolve: TraceFieldResolver;
  readonly include?: (trace: Trace) => boolean;
}

const WRAPPED_TRACE_KEYS = new Set<keyof Trace | string>([
  'id',
  'root_span_id',
  'session_id',
  'workspace',
]);

const humanizeFieldLabel = (key: string): string =>
  key
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

export type TraceKeyValueEntry = KeyValueEntry;

export interface TraceHighlightMetric extends HighlightMetric {}

interface TraceHighlightMetricDescriptor {
  readonly key: keyof Trace | string;
  readonly label: string;
  readonly resolve: (trace: Trace) => string | null | undefined;
}

/** Trace fields promoted to the top metrics card instead of the summary accordion. */
export const TRACE_HIGHLIGHT_METRIC_KEYS = new Set<keyof Trace | string>([
  'status',
  'span_count',
  'error_count',
  'duration_ms',
  'cost_usd',
  'input_tokens',
  'output_tokens',
  'total_tokens',
]);

const TRACE_HIGHLIGHT_METRIC_DESCRIPTORS: readonly TraceHighlightMetricDescriptor[] = [
  {
    key: 'span_count',
    label: 'Spans',
    resolve: (trace) =>
      trace.span_count != null ? formatInteger(trace.span_count) : undefined,
  },
  {
    key: 'error_count',
    label: 'Errors',
    resolve: (trace) =>
      trace.error_count != null ? formatInteger(trace.error_count) : undefined,
  },
  {
    key: 'duration_ms',
    label: 'Duration',
    resolve: (trace) =>
      trace.duration_ms != null ? formatDurationMs(trace.duration_ms) : undefined,
  },
  {
    key: 'cost_usd',
    label: 'Total Cost',
    resolve: (trace) => (trace.cost_usd != null ? formatCost(trace.cost_usd) : undefined),
  },
  {
    key: 'input_tokens',
    label: 'Input Tokens',
    resolve: (trace) =>
      trace.input_tokens != null ? formatInteger(trace.input_tokens) : undefined,
  },
  {
    key: 'output_tokens',
    label: 'Output Tokens',
    resolve: (trace) =>
      trace.output_tokens != null ? formatInteger(trace.output_tokens) : undefined,
  },
  {
    key: 'total_tokens',
    label: 'Total Tokens',
    resolve: (trace) =>
      trace.total_tokens != null ? formatInteger(trace.total_tokens) : undefined,
  },
];

const TRACE_SUMMARY_DESCRIPTORS: readonly TraceFieldDescriptor[] = [
  {
    key: 'started_at',
    label: 'Started',
    resolve: (trace) => formatAbsoluteTimestamp(trace.started_at),
  },
  {
    key: 'ended_at',
    label: 'Ended',
    resolve: (trace) =>
      trace.ended_at ? formatAbsoluteTimestamp(trace.ended_at) : EMPTY_VALUE,
    include: (trace) => trace.ended_at != null,
  },
  {
    key: 'name',
    label: 'Name',
    resolve: (trace) => formatMaybe(trace.name),
    include: (trace) => isMeaningfulValue(trace.name),
  },
  {
    key: 'id',
    label: 'Trace ID',
    resolve: (trace) => trace.id,
  },
  {
    key: 'root_span_id',
    label: 'Root Span',
    resolve: (trace, { workspace }) =>
      trace.root_span_id ? (
        <Link to={getIntakeSpanRoute(workspace, trace.root_span_id)} className="break-all">
          {trace.root_span_id}
        </Link>
      ) : (
        EMPTY_VALUE
      ),
    include: (trace) => isMeaningfulValue(trace.root_span_id),
  },
  {
    key: 'session_id',
    label: 'Session ID',
    resolve: (trace) => trace.session_id,
  },
  {
    key: 'workspace',
    label: 'Workspace',
    resolve: (trace) => trace.workspace,
  },
  {
    key: 'cached_tokens',
    label: 'Cached Tokens',
    resolve: (trace) =>
      trace.cached_tokens != null ? formatInteger(trace.cached_tokens) : EMPTY_VALUE,
    include: (trace) => trace.cached_tokens != null,
  },
  {
    key: 'cost_input_usd',
    label: 'Input Cost',
    resolve: (trace) =>
      trace.cost_input_usd != null ? formatCost(trace.cost_input_usd) : EMPTY_VALUE,
    include: (trace) => trace.cost_input_usd != null,
  },
  {
    key: 'cost_output_usd',
    label: 'Output Cost',
    resolve: (trace) =>
      trace.cost_output_usd != null ? formatCost(trace.cost_output_usd) : EMPTY_VALUE,
    include: (trace) => trace.cost_output_usd != null,
  },
];

const EXPERIMENT_CONTEXT_DESCRIPTORS: readonly {
  readonly key: keyof ExperimentContext | string;
  readonly label: string;
}[] = [
  { key: 'experiment_id', label: 'Experiment ID' },
  { key: 'test_case_id', label: 'Test Case ID' },
];

const collectDescriptorEntries = (
  descriptors: readonly TraceFieldDescriptor[],
  trace: Trace,
  ctx: TraceKeyValueContext
): TraceKeyValueEntry[] =>
  descriptors.flatMap((descriptor) => {
    if (descriptor.include && !descriptor.include(trace)) {
      return [];
    }

    const value = descriptor.resolve(trace, ctx);
    if (value == null || value === '') {
      return [];
    }

    return [
      {
        id: String(descriptor.key),
        label: descriptor.label,
        value,
        wrapValue: WRAPPED_TRACE_KEYS.has(descriptor.key),
      },
    ];
  });

const collectUnmappedTraceEntries = (trace: Trace): TraceKeyValueEntry[] => {
  const mappedKeys = new Set([
    ...TRACE_SUMMARY_DESCRIPTORS.map((descriptor) => descriptor.key),
    ...TRACE_HIGHLIGHT_METRIC_KEYS,
    'experiment_context',
  ]);

  return Object.entries(trace)
    .filter(([key, value]) => !mappedKeys.has(key) && isMeaningfulValue(value))
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => ({
      id: key,
      label: humanizeFieldLabel(key),
      value: formatUnknownKeyValue(value),
      wrapValue: true,
    }));
};

export const buildTraceSummaryEntries = (
  trace: Trace,
  ctx: TraceKeyValueContext
): TraceKeyValueEntry[] => [
  ...collectDescriptorEntries(TRACE_SUMMARY_DESCRIPTORS, trace, ctx),
  ...collectUnmappedTraceEntries(trace),
];

/** Builds the fixed set of headline metrics shown above the summary accordion. */
export const buildTraceHighlightMetrics = (trace: Trace): TraceHighlightMetric[] =>
  TRACE_HIGHLIGHT_METRIC_DESCRIPTORS.map((descriptor) => ({
    id: String(descriptor.key),
    label: descriptor.label,
    value: descriptor.resolve(trace) ?? EMPTY_VALUE,
  }));

export const buildExperimentContextEntries = (
  experimentContext: ExperimentContext | null | undefined
): TraceKeyValueEntry[] => {
  if (!experimentContext) {
    return [];
  }

  const mappedKeys = new Set<string>();
  const knownEntries = EXPERIMENT_CONTEXT_DESCRIPTORS.flatMap(({ key, label }) => {
    mappedKeys.add(String(key));
    const value = experimentContext[key as keyof ExperimentContext];
    if (!isMeaningfulValue(value)) {
      return [];
    }

    return [
      {
        id: String(key),
        label,
        value: String(value),
        wrapValue: true,
      },
    ];
  });

  const extraEntries = Object.entries(experimentContext)
    .filter(([key, value]) => !mappedKeys.has(key) && isMeaningfulValue(value))
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => ({
      id: key,
      label: humanizeFieldLabel(key),
      value: formatUnknownKeyValue(value),
      wrapValue: true,
    }));

  return [...knownEntries, ...extraEntries];
};
