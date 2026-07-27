// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import type { Trace } from '@nemo/sdk/generated/platform/schema';
import { Badge } from '@nvidia/foundations-react-core';
import { IntakePayloadPreviewCell } from '@studio/components/IntakeLists/IntakePayloadPreviewCell';
import type { IntakeTelemetryDataView } from '@studio/components/IntakeLists/IntakeTelemetryDataView';
import {
  formatCost,
  formatDurationMs,
  formatInteger,
  getTraceDisplayName,
} from '@studio/util/intakeTelemetry';
import type { ComponentProps } from 'react';

type MakeIntakeTraceColumns = ComponentProps<typeof IntakeTelemetryDataView<Trace>>['makeColumns'];

export interface IntakeTraceColumnOptions {
  /** Expose a Trace ID text filter on the first column (workspace browse table). */
  traceIdFilter?: boolean;
  /** Allow sorting by started_at (server-backed list only). */
  startedAtSort?: boolean;
  /** Expose a Started At datetime filter (workspace browse table). */
  startedAtFilter?: boolean;
}

/**
 * Shared trace table columns for Intake browse (`IntakeTracesTable`) and insight evidence
 * (`InsightTracesTable`). Keeps headers, sizes, and formatters in one place.
 */
export const makeIntakeTraceColumns =
  ({
    traceIdFilter = false,
    startedAtSort = false,
    startedAtFilter = false,
  }: IntakeTraceColumnOptions = {}): MakeIntakeTraceColumns =>
  ({ accessor }) => [
    accessor('id', {
      id: 'id',
      header: 'Trace',
      size: 280,
      enableSorting: false,
      meta: traceIdFilter
        ? {
            filter: {
              type: 'text' as const,
              label: 'Trace ID',
              placeholder: 'Filter by trace ID',
            },
          }
        : undefined,
      cell: ({ row }) => getTraceDisplayName(row.original),
    }),
    accessor('input', {
      id: 'input',
      header: 'Input',
      size: 360,
      enableSorting: false,
      cell: ({ row }) => <IntakePayloadPreviewCell value={row.original.input} />,
    }),
    accessor('output', {
      id: 'output',
      header: 'Output',
      size: 360,
      enableSorting: false,
      cell: ({ row }) => <IntakePayloadPreviewCell value={row.original.output} />,
    }),
    {
      id: 'duration_ms',
      header: 'Duration',
      size: 120,
      enableSorting: false,
      cell: ({ row }) => formatDurationMs(row.original.duration_ms),
    },
    {
      id: 'span_count',
      header: 'Spans',
      size: 90,
      enableSorting: false,
      cell: ({ row }) => formatInteger(row.original.span_count),
    },
    {
      id: 'error_count',
      header: 'Errors',
      size: 90,
      enableSorting: false,
      cell: ({ row }) => {
        const errorCount = row.original.error_count ?? 0;
        return errorCount > 0 ? (
          <Badge kind="solid" color="red">
            {formatInteger(errorCount)}
          </Badge>
        ) : (
          formatInteger(errorCount)
        );
      },
    },
    {
      id: 'total_tokens',
      header: 'Tokens',
      size: 120,
      enableSorting: false,
      cell: ({ row }) => formatInteger(row.original.total_tokens),
    },
    {
      id: 'cost_usd',
      header: 'Cost',
      size: 110,
      enableSorting: false,
      cell: ({ row }) => formatCost(row.original.cost_usd),
    },
    accessor('started_at', {
      id: 'started_at',
      header: 'Started',
      size: 150,
      enableSorting: startedAtSort,
      meta: startedAtFilter ? { filter: dateTimeFilter('Started At') } : undefined,
      cell: ({ row }) => <RelativeTime datetime={row.original.started_at} />,
    }),
  ];
