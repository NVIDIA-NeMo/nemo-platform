// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  formatAbsoluteTimestamp,
  parseISOWithUTCFallback,
} from '@nemo/common/src/components/RelativeTime/util';
import type { Span } from '@nemo/sdk/generated/platform/schema';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { IntakeTelemetryStatusBadge } from '@studio/components/IntakeDetail/IntakeComponents/IntakeTelemetryStatusBadge';
import { KeyValueGrid } from '@studio/components/IntakeDetail/IntakeComponents/KeyValueGrid';
import type { RankedDocument } from '@studio/components/IntakeDetail/SpanTemplates/rawAttributes';
import { EMPTY_VALUE } from '@studio/util/intakeTelemetry';
import { type FC, type ReactNode, useState } from 'react';

export interface TemplateField {
  label: string;
  value: ReactNode;
}

const pad2 = (value: number): string => String(value).padStart(2, '0');

/** Compact "MM/DD HH:MM" (24h) form of a timestamp. */
const formatCompactTimestamp = (iso: string): string => {
  const date = parseISOWithUTCFallback(iso);
  return `${pad2(date.getMonth() + 1)}/${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
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
 * Status and timing fields shown at the start of every template's top-level
 * values section, mirroring the Metadata section so reviewers see them up
 * front. Ended is omitted while a span is still running.
 */
const commonSpanFields = (span: Span): TemplateField[] => [
  { label: 'Status', value: <IntakeTelemetryStatusBadge status={span.status} /> },
  { label: 'Started', value: <TimestampToggle iso={span.started_at} /> },
  { label: 'Ended', value: span.ended_at ? <TimestampToggle iso={span.ended_at} /> : undefined },
];

/**
 * Shared key/value header used at the top of every span kind template. The
 * common status/timing fields lead, followed by the kind-specific `fields`.
 * Fields flow into as many equal columns as fit (auto-fit, min column width),
 * so the same component reads consistently across kinds.
 */
export const TemplateKeyValues: FC<{ span: Span; fields: TemplateField[] }> = ({
  span,
  fields,
}) => (
  <KeyValueGrid
    items={[...commonSpanFields(span), ...fields].map((field) => ({
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
