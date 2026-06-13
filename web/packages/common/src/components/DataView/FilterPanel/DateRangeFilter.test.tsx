// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DateTimeFilterControl } from '@nemo/common/src/components/DataView/FilterPanel/DateRangeFilter';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@nemo/common/src/utils/formatDateRange', () => ({
  parseUTCDateForPicker: (s: string) => new Date(s),
}));

vi.mock('@nvidia/foundations-react-core', () => ({
  DatePicker: ({
    'data-testid': testId,
    onValueChange,
  }: {
    'data-testid'?: string;
    onValueChange?: (value: { from?: Date; to?: Date } | undefined) => void;
    [key: string]: unknown;
  }) => (
    <div data-testid={testId}>
      <button data-testid={`${testId}-clear`} onClick={() => onValueChange?.(undefined)}>
        Clear
      </button>
      <button
        data-testid={`${testId}-set`}
        onClick={() =>
          onValueChange?.({
            from: new Date('2024-01-01T00:00:00.000Z'),
            to: new Date('2024-01-31T00:00:00.000Z'),
          })
        }
      >
        Set
      </button>
    </div>
  ),
}));

function makeColumn(filterValue?: unknown) {
  return {
    id: 'created_at',
    getCanFilter: () => true,
    getFilterValue: () => filterValue,
    setFilterValue: vi.fn(),
    columnDef: {
      header: 'Created At',
      meta: {
        filter: {
          type: 'custom',
          filterVariant: 'datetime',
          label: 'Created At',
          renderFilter: () => <></>,
        },
      },
    },
  };
}

describe('DateTimeFilterControl', () => {
  it('calls setFilterValue(undefined) when cleared', () => {
    const col = makeColumn({ $gte: '2024-01-01T00:00:00.000Z' });

    render(<DateTimeFilterControl column={col as never} />);

    fireEvent.click(screen.getByTestId('column-filter-created_at-clear'));

    expect(col.setFilterValue).toHaveBeenCalledWith(undefined);
  });

  it('calls setFilterValue with $gte/$lte when dates selected', () => {
    const col = makeColumn();

    render(<DateTimeFilterControl column={col as never} />);

    fireEvent.click(screen.getByTestId('column-filter-created_at-set'));

    expect(col.setFilterValue).toHaveBeenCalledWith({
      $gte: '2024-01-01T00:00:00.000Z',
      $lte: '2024-01-31T23:59:59.999Z',
    });
  });
});
