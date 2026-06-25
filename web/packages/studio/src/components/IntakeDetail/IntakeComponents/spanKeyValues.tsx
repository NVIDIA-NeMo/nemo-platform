// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Data-builder module: exports functions that assemble key/value entries (some
// producing JSX such as status badges and links). Not a component module.
/* eslint-disable react-refresh/only-export-components */

import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import type { Span } from '@nemo/sdk/generated/platform/schema';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeDetail/IntakeComponents/IntakeTelemetryStatusBadge';
import {
  formatUnknownKeyValue,
  isMeaningfulValue,
} from '@studio/components/IntakeDetail/IntakeComponents/keyValueFormatting';
import type { KeyValueEntry } from '@studio/components/IntakeDetail/IntakeComponents/keyValueTypes';
import { parseRawAttributes } from '@studio/components/IntakeDetail/SpanTemplates/rawAttributes';
import { getSpanTemplate } from '@studio/components/IntakeDetail/SpanTemplates/registry';
import { getIntakeSpanRoute, getIntakeTraceRoute } from '@studio/routes/utils';
import {
  EMPTY_VALUE,
  formatCost,
  formatDurationMs,
  formatInteger,
  formatMaybe,
  getEvaluationContextSummary,
  getSpanDurationMs,
  hasEvaluationContext,
} from '@studio/util/intakeTelemetry';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

interface SpanKeyValueContext {
  workspace: string;
}

type SpanFieldResolver = (span: Span, ctx: SpanKeyValueContext) => ReactNode | null | undefined;

interface SpanFieldDescriptor {
  readonly key: keyof Span | string;
  readonly label: string;
  readonly resolve: SpanFieldResolver;
  readonly include?: (span: Span) => boolean;
}

/** Fields rendered in the LLM, tokens, & cost accordion (not span summary). */
export const SPAN_LLM_ACCORDION_FIELD_KEYS = new Set<keyof Span | string>([
  'model',
  'provider',
  'prompt_id',
  'input_tokens',
  'output_tokens',
  'cached_tokens',
  'total_tokens',
  'cost_input_usd',
  'cost_output_usd',
  'cost_total_usd',
  'usage_details',
  'cost_details',
]);

const SPAN_LLM_DESCRIPTORS: readonly SpanFieldDescriptor[] = [
  {
    key: 'model',
    label: 'Model',
    resolve: (span) => formatMaybe(span.model),
    include: (span) => isMeaningfulValue(span.model),
  },
  {
    key: 'provider',
    label: 'Provider',
    resolve: (span) => formatMaybe(span.provider),
    include: (span) => isMeaningfulValue(span.provider),
  },
  {
    key: 'prompt_id',
    label: 'Prompt ID',
    resolve: (span) => formatMaybe(span.prompt_id),
    include: (span) => isMeaningfulValue(span.prompt_id),
  },
  {
    key: 'input_tokens',
    label: 'Input Tokens',
    resolve: (span) => (span.input_tokens != null ? formatInteger(span.input_tokens) : undefined),
    include: (span) => span.input_tokens != null,
  },
  {
    key: 'output_tokens',
    label: 'Output Tokens',
    resolve: (span) => (span.output_tokens != null ? formatInteger(span.output_tokens) : undefined),
    include: (span) => span.output_tokens != null,
  },
  {
    key: 'cached_tokens',
    label: 'Cached Tokens',
    resolve: (span) => (span.cached_tokens != null ? formatInteger(span.cached_tokens) : undefined),
    include: (span) => span.cached_tokens != null,
  },
  {
    key: 'total_tokens',
    label: 'Total Tokens',
    resolve: (span) => (span.total_tokens != null ? formatInteger(span.total_tokens) : undefined),
    include: (span) => span.total_tokens != null,
  },
  {
    key: 'cost_input_usd',
    label: 'Input Cost',
    resolve: (span) => (span.cost_input_usd != null ? formatCost(span.cost_input_usd) : undefined),
    include: (span) => span.cost_input_usd != null,
  },
  {
    key: 'cost_output_usd',
    label: 'Output Cost',
    resolve: (span) =>
      span.cost_output_usd != null ? formatCost(span.cost_output_usd) : undefined,
    include: (span) => span.cost_output_usd != null,
  },
  {
    key: 'cost_total_usd',
    label: 'Total Cost',
    resolve: (span) => (span.cost_total_usd != null ? formatCost(span.cost_total_usd) : undefined),
    include: (span) => span.cost_total_usd != null,
  },
  {
    key: 'usage_details',
    label: 'Usage Details',
    resolve: (span) => formatUnknownKeyValue(span.usage_details),
    include: (span) => isMeaningfulValue(span.usage_details),
  },
  {
    key: 'cost_details',
    label: 'Cost Details',
    resolve: (span) => formatUnknownKeyValue(span.cost_details),
    include: (span) => isMeaningfulValue(span.cost_details),
  },
];

const WRAPPED_SPAN_KEYS = new Set<keyof Span | string>([
  'span_id',
  'trace_id',
  'parent_span_id',
  'session_id',
  'workspace',
  'project',
  'model',
  'provider',
  'prompt_id',
  'agent_id',
  'agent_name',
  'tool_name',
]);

const humanizeFieldLabel = (key: string): string =>
  key
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

const SPAN_SUMMARY_DESCRIPTORS: readonly SpanFieldDescriptor[] = [
  {
    key: 'status',
    label: 'Status',
    resolve: (span) => <IntakeTelemetryStatusBadge status={span.status} />,
  },
  {
    key: 'kind',
    label: 'Kind',
    resolve: (span) => span.kind,
  },
  {
    key: 'span_id',
    label: 'Span ID',
    resolve: (span) => span.span_id,
  },
  {
    key: 'name',
    label: 'Name',
    resolve: (span) => formatMaybe(span.name),
    include: (span) => isMeaningfulValue(span.name),
  },
  {
    key: 'source',
    label: 'Source',
    resolve: (span) => formatMaybe(span.source),
    include: (span) => isMeaningfulValue(span.source),
  },
  {
    key: 'trace_id',
    label: 'Trace',
    resolve: (span, { workspace }) =>
      span.trace_id ? (
        <Link to={getIntakeTraceRoute(workspace, span.trace_id)}>{span.trace_id}</Link>
      ) : (
        EMPTY_VALUE
      ),
    include: (span) => isMeaningfulValue(span.trace_id),
  },
  {
    key: 'parent_span_id',
    label: 'Parent Span',
    resolve: (span, { workspace }) =>
      span.parent_span_id ? (
        <Link to={getIntakeSpanRoute(workspace, span.parent_span_id)}>{span.parent_span_id}</Link>
      ) : (
        EMPTY_VALUE
      ),
    include: (span) => isMeaningfulValue(span.parent_span_id),
  },
  {
    key: 'started_at',
    label: 'Started',
    resolve: (span) => formatAbsoluteTimestamp(span.started_at),
  },
  {
    key: 'ended_at',
    label: 'Ended',
    resolve: (span) => (span.ended_at ? formatAbsoluteTimestamp(span.ended_at) : EMPTY_VALUE),
    include: (span) => span.ended_at != null,
  },
  {
    key: 'duration',
    label: 'Duration',
    resolve: (span) => formatDurationMs(getSpanDurationMs(span)),
    include: (span) => getSpanDurationMs(span) != null,
  },
  {
    key: 'session_id',
    label: 'Session ID',
    resolve: (span) => span.session_id,
  },
  {
    key: 'workspace',
    label: 'Workspace',
    resolve: (span) => span.workspace,
  },
  {
    key: 'project',
    label: 'Project',
    resolve: (span) => formatMaybe(span.project),
    include: (span) => isMeaningfulValue(span.project),
  },
  {
    key: 'agent_name',
    label: 'Agent',
    resolve: (span) => formatMaybe(span.agent_name),
    include: (span) => isMeaningfulValue(span.agent_name),
  },
  {
    key: 'tool_name',
    label: 'Tool',
    resolve: (span) => formatMaybe(span.tool_name),
    include: (span) => isMeaningfulValue(span.tool_name),
  },
  {
    key: 'evaluation_context',
    label: 'Evaluation',
    resolve: (span) => getEvaluationContextSummary(span.evaluation_context),
    include: (span) => hasEvaluationContext(span.evaluation_context),
  },
  {
    key: 'error_type',
    label: 'Error Type',
    resolve: (span) => formatMaybe(span.error_type),
    include: (span) => span.status === 'error' && isMeaningfulValue(span.error_type),
  },
  {
    key: 'error_message',
    label: 'Error Message',
    resolve: (span) => formatMaybe(span.error_message),
    include: (span) => span.status === 'error' && isMeaningfulValue(span.error_message),
  },
];

const collectDescriptorEntries = (
  descriptors: readonly SpanFieldDescriptor[],
  span: Span,
  ctx: SpanKeyValueContext
): KeyValueEntry[] =>
  descriptors.flatMap((descriptor) => {
    if (descriptor.include && !descriptor.include(span)) {
      return [];
    }

    const value = descriptor.resolve(span, ctx);
    if (value == null || value === '') {
      return [];
    }

    return [
      {
        id: String(descriptor.key),
        label: descriptor.label,
        value,
        wrapValue: WRAPPED_SPAN_KEYS.has(descriptor.key),
      },
    ];
  });

const collectUnmappedSpanEntries = (span: Span): KeyValueEntry[] => {
  const mappedKeys = new Set([
    ...SPAN_SUMMARY_DESCRIPTORS.map((descriptor) => descriptor.key),
    ...SPAN_LLM_DESCRIPTORS.map((descriptor) => descriptor.key),
    'input',
    'output',
    'evaluation_context',
    'raw_attributes',
    'ingested_at',
  ]);

  return Object.entries(span)
    .filter(([key, value]) => !mappedKeys.has(key) && isMeaningfulValue(value))
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => ({
      id: key,
      label: humanizeFieldLabel(key),
      value: formatUnknownKeyValue(value),
      wrapValue: true,
    }));
};

const SPAN_LLM_ALWAYS_SHOW_KEYS = new Set<keyof Span | string>([
  'model',
  'provider',
  'input_tokens',
  'output_tokens',
  'cached_tokens',
  'total_tokens',
  'cost_input_usd',
  'cost_output_usd',
  'cost_total_usd',
]);

const hasFieldValue = (value: unknown): boolean => {
  if (value === null || value === undefined || value === '') {
    return false;
  }
  if (typeof value === 'object' && !Array.isArray(value)) {
    return Object.keys(value).length > 0;
  }
  return true;
};

/** Prefer detailed span fields, but backfill LLM metrics from list/summary rows when absent. */
export const mergeSpanDetails = (summarySpan: Span | undefined, detailSpan: Span): Span => {
  if (!summarySpan) {
    return detailSpan;
  }

  const merged: Span = { ...detailSpan };

  for (const key of SPAN_LLM_ACCORDION_FIELD_KEYS) {
    const detailValue = merged[key as keyof Span];
    const summaryValue = summarySpan[key as keyof Span];
    if (!hasFieldValue(detailValue) && hasFieldValue(summaryValue)) {
      (merged as unknown as Record<string, unknown>)[key] = summaryValue;
    }
  }

  return merged;
};

const collectLlmEntries = (span: Span): KeyValueEntry[] =>
  SPAN_LLM_DESCRIPTORS.flatMap((descriptor) => {
    const alwaysShow = SPAN_LLM_ALWAYS_SHOW_KEYS.has(descriptor.key);
    if (!alwaysShow && descriptor.include && !descriptor.include(span)) {
      return [];
    }

    const value = descriptor.resolve(span, { workspace: span.workspace });
    const displayValue = value == null || value === '' ? EMPTY_VALUE : value;

    return [
      {
        id: String(descriptor.key),
        label: descriptor.label,
        value: displayValue,
        wrapValue: WRAPPED_SPAN_KEYS.has(descriptor.key),
      },
    ];
  });

export const buildSpanLlmEntries = (span: Span): KeyValueEntry[] => collectLlmEntries(span);

/** True when `key` sits under one of the dotted `namespaces` (exact or prefix). */
const isUnderNamespace = (key: string, namespaces: readonly string[]): boolean =>
  namespaces.some((namespace) => key === namespace || key.startsWith(`${namespace}.`));

/**
 * Raw-attribute entries for the Metadata section, keyed by their original dotted
 * name. Attributes whose namespace a kind template has claimed
 * (`attributeNamespaces`) are skipped — they're already rendered in that
 * template's section/header, so Metadata stays a dump of only what hasn't been
 * purposefully surfaced. Excluding nothing extra keeps it maintenance-free.
 */
const collectRawAttributeEntries = (span: Span): KeyValueEntry[] => {
  const claimedNamespaces = getSpanTemplate(span.kind).attributeNamespaces ?? [];
  return Object.entries(parseRawAttributes(span.raw_attributes))
    .filter(([key, value]) => isMeaningfulValue(value) && !isUnderNamespace(key, claimedNamespaces))
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => ({
      id: `raw:${key}`,
      label: key,
      value: formatUnknownKeyValue(value),
      wrapValue: true,
    }));
};

/**
 * Span fields already surfaced elsewhere in the detail view, so Metadata omits
 * them: `status`, `started_at`, and `ended_at` lead every span template's
 * key/value header (see `commonSpanFields`), `duration` is always in the
 * row-header/trigger metrics, and the error fields appear in the error banner.
 */
const renderedElsewhereSpanKeys = (span: Span): ReadonlySet<string> => {
  const keys = new Set<string>(['status', 'started_at', 'ended_at', 'duration']);
  if (span.status === 'error') {
    keys.add('error_type');
    keys.add('error_message');
  }
  return keys;
};

export const buildSpanSummaryEntries = (span: Span, ctx: SpanKeyValueContext): KeyValueEntry[] => {
  const renderedElsewhere = renderedElsewhereSpanKeys(span);
  return [
    ...collectDescriptorEntries(SPAN_SUMMARY_DESCRIPTORS, span, ctx).filter(
      (entry) => !renderedElsewhere.has(entry.id)
    ),
    ...collectUnmappedSpanEntries(span),
    ...collectRawAttributeEntries(span),
  ];
};
