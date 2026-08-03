// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { StudioDataView } from '@nemo/common/src/components/DataView/StudioDataView';
import { TableEmptyState } from '@nemo/common/src/components/TableEmptyState';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { Button, Text } from '@nvidia/foundations-react-core';
import type { GuardrailCheckEntity, Verdict } from '@studio/api/guardrail-checks/types';
import {
  getCheckInputText,
  getCheckOutputText,
} from '@studio/components/dataViews/GuardrailChecksDataView/checkMessages';
import {
  getLatestRunStatus,
  getResultFilterValue,
  getResultSortRank,
  RESULT_FILTER_OPTIONS,
} from '@studio/components/dataViews/GuardrailChecksDataView/checkStatus';
import { ResultIndicator } from '@studio/components/dataViews/GuardrailChecksDataView/ResultIndicator';
import { ListChecks } from 'lucide-react';
import { type ComponentProps, type FC, useCallback, useMemo } from 'react';

export interface GuardrailChecksDataViewProps {
  checks: GuardrailCheckEntity[];
}

/** One check flattened to the values the table searches, filters, sorts, and renders. */
interface GuardrailCheckRow {
  id: string;
  input: string;
  output: string;
  status: Verdict | undefined;
}

const RESULT_COLUMN_ID = 'status';

/**
 * Table of a guardrail config's test cases and their latest result.
 *
 * Checks arrive as a prop because the parent already loads the full set for the Tests sub-tab,
 * so search, filtering, sorting, and pagination are all applied client-side here.
 */
export const GuardrailChecksDataView: FC<GuardrailChecksDataViewProps> = ({ checks }) => {
  // No default sort: unsorted order matches the Tests sub-tab's card order (Test 1, Test 2, …).
  const dataViewState = useStudioDataViewState();

  const rows = useMemo<GuardrailCheckRow[]>(
    () =>
      checks.map((check) => ({
        id: check.id,
        input: getCheckInputText(check.data.messages),
        output: getCheckOutputText(check.data.messages),
        status: getLatestRunStatus(check),
      })),
    [checks]
  );

  const { debouncedSearchBar, debouncedColumnFilters } = dataViewState;

  const filteredRows = useMemo(() => {
    const search = debouncedSearchBar.trim().toLowerCase();
    const resultFilter = debouncedColumnFilters.find((filter) => filter.id === RESULT_COLUMN_ID)
      ?.value as string | undefined;

    return rows.filter((row) => {
      if (search) {
        const haystack = `${row.input} ${row.output}`.toLowerCase();
        if (!haystack.includes(search)) {
          return false;
        }
      }
      return !resultFilter || getResultFilterValue(row.status) === resultFilter;
    });
  }, [rows, debouncedSearchBar, debouncedColumnFilters]);

  const sortState = dataViewState.sorting.state[0];
  const sortedRows = useMemo(() => {
    if (sortState?.id !== RESULT_COLUMN_ID) {
      return filteredRows;
    }
    return [...filteredRows].sort((a, b) => {
      const cmp = getResultSortRank(a.status) - getResultSortRank(b.status);
      return sortState.desc ? -cmp : cmp;
    });
  }, [filteredRows, sortState]);

  const { pageIndex, pageSize } = dataViewState.pagination.state;
  const pageRows = useMemo(() => {
    const start = pageIndex * pageSize;
    return sortedRows.slice(start, start + pageSize);
  }, [sortedRows, pageIndex, pageSize]);

  const makeColumns: ComponentProps<typeof StudioDataView<GuardrailCheckRow>>['makeColumns'] =
    useCallback(
      ({ accessor }) => [
        accessor('input', {
          header: 'Input',
          enableSorting: false,
          cell({ row }) {
            const { input } = row.original;
            return <Text title={input}>{input || '—'}</Text>;
          },
        }),
        accessor('output', {
          header: 'Output',
          enableSorting: false,
          cell({ row }) {
            const { output } = row.original;
            return <Text title={output}>{output || '—'}</Text>;
          },
        }),
        accessor(RESULT_COLUMN_ID, {
          header: 'Result',
          enableSorting: true,
          size: 160,
          meta: {
            filter: {
              type: 'single-select',
              label: 'Result',
              options: RESULT_FILTER_OPTIONS,
            },
          },
          cell({ row }) {
            return <ResultIndicator status={row.original.status} />;
          },
        }),
      ],
      []
    );

  const hasSearchOrFilters = !!debouncedSearchBar || debouncedColumnFilters.length > 0;

  return (
    <StudioDataView<GuardrailCheckRow>
      dataViewState={dataViewState}
      searchField="input"
      makeColumns={makeColumns}
      attributes={{
        DataViewSearchBar: { placeholder: 'Search tests...' },
        DataViewRoot: {
          data: pageRows,
          totalCount: filteredRows.length,
        },
        DataViewTableContent: {
          renderEmptyState: () =>
            hasSearchOrFilters ? (
              <TableEmptyState
                header="No Results Found"
                emptyMessage="No tests match your search or filters"
                actions={
                  <Button kind="tertiary" onClick={dataViewState.resetFilters}>
                    Clear Filters
                  </Button>
                }
              />
            ) : (
              <TableEmptyState
                icon={<ListChecks className="size-16" />}
                header="No tests yet"
                emptyMessage="Add a test case on the Tests tab, then run it to see its result here."
              />
            ),
        },
      }}
    />
  );
};
