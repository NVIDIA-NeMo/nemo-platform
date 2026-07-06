// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NumberRangeFilterControl } from '@nemo/common/src/components/DataView/FilterPanel/NumberRangeFilter';
import { numberRangeFilter } from '@nemo/common/src/components/DataView/FilterPanel/NumberRangeFilter/util';
import { useCustomReactTable } from '@nemo/common/src/components/DataView/internal/hooks/useCustomReactTable';
import { useMakeColumns } from '@nemo/common/src/components/DataView/internal/hooks/useMakeColumns';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/**
 * Integration tests for the end-to-end range-filter path used by server-side (manual) data views:
 * a numeric column with a `numberRange` filter, built through the real `useMakeColumns` and wired to
 * a real TanStack table via `useCustomReactTable`, must commit a `{ $gte, $lte }` value that then
 * surfaces (remapped via `filterFieldMap`) in `apiFilter.filter` — the object that keys the request.
 *
 * These exercise the real hooks/components (no mocks). Crucially the harness feeds **numeric** rows,
 * so without an explicit `numberRange` filterFn TanStack would resolve the column to its built-in
 * `inNumberRange`, whose `autoRemove` drops the `{ $gte, $lte }` object and silently kills the
 * filter (the production bug this guards against).
 */

interface Row {
  latency_ms?: { mean?: number };
}

// Numeric rows so TanStack's auto filterFn resolution would pick `inNumberRange` without the fix.
const DATA: Row[] = [
  { latency_ms: { mean: 5 } },
  { latency_ms: { mean: 150 } },
  { latency_ms: { mean: 500 } },
];

function useHarness() {
  const dataViewState = useStudioDataViewState({
    filterFieldMap: { latency_ms: 'latency_ms.mean' },
  });
  const columns = useMakeColumns<Row>({
    makeColumns: (columnHelper) => [
      columnHelper.accessor((r) => r.latency_ms?.mean, {
        id: 'latency_ms',
        header: 'Avg Latency',
        meta: { filter: numberRangeFilter('Avg Latency') },
      }),
    ],
    overrideToLoadingCells: false,
  });
  const table = useCustomReactTable<Row>({
    columns,
    data: DATA,
    dataMode: 'manual',
    state: dataViewState,
    totalCount: DATA.length,
  });
  return { dataViewState, table };
}

describe('useStudioDataViewState range-filter integration', () => {
  it('assigns the numberRange filterFn so setFilterValue commits (not auto-removed)', async () => {
    const { result } = renderHook(() => useHarness(), { wrapper: MemoryRouter });

    // Regression guard: the column must not fall through to TanStack's `inNumberRange`.
    expect(result.current.table.getColumn('latency_ms')?.columnDef.filterFn).toBe('numberRange');
    expect(result.current.dataViewState.apiFilter.filter).toBeUndefined();

    act(() => {
      result.current.table.getColumn('latency_ms')?.setFilterValue({ $gte: 5, $lte: undefined });
    });

    await waitFor(
      () =>
        expect(result.current.dataViewState.apiFilter.filter).toEqual({
          'latency_ms.mean': { $gte: 5 },
        }),
      { timeout: 2000 }
    );
  });

  it('emits both bounds under the dotted API key for a closed range', async () => {
    const { result } = renderHook(() => useHarness(), { wrapper: MemoryRouter });

    act(() => {
      result.current.table.getColumn('latency_ms')?.setFilterValue({ $gte: 5, $lte: 250 });
    });

    await waitFor(
      () =>
        expect(result.current.dataViewState.apiFilter.filter).toEqual({
          'latency_ms.mean': { $gte: 5, $lte: 250 },
        }),
      { timeout: 2000 }
    );
  });

  it('drives apiFilter from the rendered range control (type + blur)', async () => {
    function Harness() {
      const { dataViewState, table } = useHarness();
      const column = table.getColumn('latency_ms');
      return (
        <>
          {column ? <NumberRangeFilterControl column={column as never} /> : null}
          <div data-testid="api-filter">
            {JSON.stringify(dataViewState.apiFilter.filter ?? null)}
          </div>
        </>
      );
    }

    render(<Harness />, { wrapper: MemoryRouter });

    const min = screen.getByPlaceholderText('Min');
    fireEvent.change(min, { target: { value: '100' } });
    fireEvent.blur(min);

    await waitFor(
      () =>
        expect(screen.getByTestId('api-filter').textContent).toBe(
          JSON.stringify({ 'latency_ms.mean': { $gte: 100 } })
        ),
      { timeout: 2000 }
    );
  });
});
