// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KeyValueGrid } from '@nemo/common/src/components/KeyValueGrid';
import {
  formatAbsoluteTimestamp,
  parseISOWithUTCFallback,
} from '@nemo/common/src/components/RelativeTime/util';
import type { Span } from '@nemo/sdk/generated/platform/schema';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeDetail/IntakeComponents/IntakeTelemetryStatusBadge';
import type { RankedDocument } from '@studio/components/IntakeDetail/SpanTemplates/rawAttributes';
import { EMPTY_VALUE } from '@studio/util/intakeTelemetry';
import { type FC, type ReactNode, useState } from 'react';

export interface TemplateField {
  label: string;
  value: ReactNode;
}

/** Compact "MM/DD HH:MM" (24h) form of a timestamp. */
const formatCompactTimestamp = (iso: string): string => {
  const date = parseISOWithUTCFallback(iso);
  // Mirror formatAbsoluteTimestamp's Intl.DateTimeFormat('en-US') usage so the
  // compact and full forms stay consistent.
  const userLocale = navigator.language;
  const options: Intl.DateTimeFormatOptions = {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  };
  const formatter = new Intl.DateTimeFormat(userLocale, options);
  return formatter.format(date).replace(',', '');
};

/** Compact timestamp that swaps to the full, absolute timestamp when clicked. */
const TimestampToggle: FC<{ iso: string }> = ({ iso }) => {
  const [showFull, setShowFull] = useState(false);
  return (
    <button
      type="button"
      onClick={() => setShowFull((value) => !value)}
      className="cursor-pointer text-left underline decoration-dotted decoration-from-font underline-offset-2"
      title="Click to toggle full timestamp"
    >
      {showFull ? formatAbsoluteTimestamp(iso) : formatCompactTimestamp(iso)}
    </button>
  );
};

/**
 * Status field shown first in every template's top-level values section,
 * mirroring the row-header status badge.
 */
const statusField = (span: Span): TemplateField => ({
  label: 'Status',
  value: <IntakeTelemetryStatusBadge status={span.status} />,
});

/**
 * Timing fields shown last in every template's top-level values section, after
 * the kind-specific fields. Ended is omitted while a span is still running.
 */
const timingFields = (span: Span): TemplateField[] => [
  { label: 'Started', value: <TimestampToggle iso={span.started_at} /> },
  { label: 'Ended', value: span.ended_at ? <TimestampToggle iso={span.ended_at} /> : undefined },
];

/**
 * Shared key/value header used at the top of every span kind template. Status
 * leads, the kind-specific `fields` follow, and the timing fields trail at the
 * end. Fields flow into as many equal columns as fit (auto-fit, min column
 * width), so the same component reads consistently across kinds.
 */
export const TemplateKeyValues: FC<{ span: Span; fields: TemplateField[] }> = ({
  span,
  fields,
}) => (
  <KeyValueGrid
    items={[statusField(span), ...fields, ...timingFields(span)].map((field) => ({
      key: field.label,
      label: field.label,
      value: field.value,
    }))}
  />
);

const formatScore = (score: number | undefined): string =>
  score === undefined ? EMPTY_VALUE : score.toFixed(3);

/** Ranked, scored document list shared by the retriever and reranker templates. */
export const RankedDocumentList: FC<{ documents: RankedDocument[]; emptyMessage: string }> = ({
  documents,
  emptyMessage,
}) => {
  if (documents.length === 0) {
    return (
      <div className="flex min-h-[80px] items-center rounded-md border border-dashed border-base bg-surface-raised p-density-xl">
        <Text kind="body/regular/sm" className="text-secondary">
          {emptyMessage}
        </Text>
      </div>
    );
  }
  return (
    <Stack gap="density-md">
      {documents.map((document) => (
        <Stack
          key={`${document.rank}-${document.id ?? 'doc'}`}
          gap="density-sm"
          className="rounded-md border border-base bg-surface-raised p-density-lg min-w-0"
        >
          <div className="flex items-center justify-between gap-density-md">
            <Text kind="label/bold/sm">
              {`#${document.rank}`}
              {document.id ? <span className="text-secondary"> · {document.id}</span> : null}
            </Text>
            <Text kind="label/regular/sm" className="text-secondary">
              {`score ${formatScore(document.score)}`}
            </Text>
          </div>
          {document.content ? (
            <Text kind="body/regular/sm" className="break-words text-secondary line-clamp-4">
              {document.content}
            </Text>
          ) : null}
        </Stack>
      ))}
    </Stack>
  );
};
