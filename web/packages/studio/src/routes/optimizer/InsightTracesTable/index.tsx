// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EditColumnsMenu } from '@nemo/common/src/components/DataView/internal';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { getGetTraceQueryKey, getTrace } from '@nemo/sdk/generated/platform/api';
import type { Trace } from '@nemo/sdk/generated/platform/schema';
import { Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { makeIntakeTraceColumns } from '@studio/components/IntakeLists/intakeTraceColumns';
import { IntakeTelemetryDataView } from '@studio/components/IntakeLists/IntakeTelemetryDataView';
import { getIntakeTraceRoute } from '@studio/routes/utils';
import { useQueries } from '@tanstack/react-query';
import { Columns3, TriangleAlert } from 'lucide-react';
import { type FC } from 'react';
import { useNavigate } from 'react-router-dom';

export interface InsightTracesTableProps {
  workspace: string;
  /** Intake trace ids (the insight's `trace_refs`). */
  traceIds: string[];
}

/**
 * Renders an insight's evidence traces using the same columns and DataView shell as
 * `IntakeTracesTable`. Unlike the workspace browse table, this fetches only the referenced
 * traces by id and preserves `traceIds` order (no server sort/filter).
 */
export const InsightTracesTable: FC<InsightTracesTableProps> = ({ workspace, traceIds }) => {
  const navigate = useNavigate();
  const dataViewState = useStudioDataViewState();

  const results = useQueries({
    queries: traceIds.map((id) => ({
      queryKey: getGetTraceQueryKey(workspace, id),
      queryFn: ({ signal }: { signal: AbortSignal }) => getTrace(workspace, id, undefined, signal),
      enabled: Boolean(workspace) && Boolean(id),
    })),
  });

  const traces = results.map((r) => r.data).filter((t): t is Trace => Boolean(t));
  const isFetching = results.some((r) => r.isFetching);
  const failedCount = results.filter((r) => r.isError).length;
  const allFailed = traceIds.length > 0 && failedCount === traceIds.length && !isFetching;
  const firstError = results.find((r) => r.error)?.error;

  return (
    <Stack className="gap-density-sm">
      {failedCount > 0 && !allFailed ? (
        <Flex className="items-center gap-density-sm">
          <TriangleAlert aria-hidden className="size-4 shrink-0 text-danger" />
          <Text kind="body/regular/sm" className="text-danger">
            {failedCount} of {traceIds.length} traces couldn&apos;t be loaded.
          </Text>
        </Flex>
      ) : null}
      <IntakeTelemetryDataView<Trace>
        dataViewState={dataViewState}
        makeColumns={makeIntakeTraceColumns()}
        onRowClick={(trace) => navigate(getIntakeTraceRoute(workspace, trace.id))}
        toolbarSlotEnd={
          <EditColumnsMenu
            kind="secondary"
            showChevron={false}
            slotContent={<div aria-hidden className="h-0 w-[230px]" />}
          >
            <>
              <Columns3 />
              <span className="hide-mobile">Columns</span>
            </>
          </EditColumnsMenu>
        }
        attributes={{
          DataViewRoot: {
            data: traces,
            totalCount: traces.length,
            requestStatus: allFailed ? 'error' : isFetching ? 'loading' : undefined,
          },
          DataViewTableContent: {
            renderEmptyState: () => (
              <TableEmptyState
                header="No traces"
                emptyMessage="This insight has no linked traces."
              />
            ),
            renderErrorState: () => (
              <ErrorMessage
                message={getErrorMessage(firstError ?? new Error('Failed to load traces'))}
              />
            ),
          },
        }}
      />
    </Stack>
  );
};
