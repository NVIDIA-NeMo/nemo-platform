// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ColumnFilterPanel } from '@nemo/common/src/components/DataView/ColumnFilterPanel';
import { dateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import { render, screen } from '@testing-library/react';

const mockColumns: Array<Record<string, unknown>> = [];

vi.mock('@nemo/common/src/components/DataView/internal', () => ({
  useInnerDataViewContext: () => ({
    table: {
      getAllLeafColumns: () => mockColumns,
    },
  }),
}));

vi.mock('@nemo/common/src/components/DataView/FilterPanel', () => ({
  TextFilterControl: ({ column }: { column: { id: string } }) => (
    <div data-testid={`column-filter-${column.id}`}>TextFilter</div>
  ),
  BooleanFilterControl: ({ column }: { column: { id: string } }) => (
    <div data-testid={`column-filter-${column.id}`}>BooleanFilter</div>
  ),
  SingleSelectFilterControl: ({ column }: { column: { id: string } }) => (
    <div data-testid={`column-filter-${column.id}`}>SingleSelectFilter</div>
  ),
  MultiSelectFilterControl: ({ column }: { column: { id: string } }) => (
    <div data-testid={`column-filter-${column.id}`}>MultiSelectFilter</div>
  ),
  DateTimeFilterControl: ({ column }: { column: { id: string } }) => (
    <div data-testid={`column-filter-${column.id}`}>DateTimeFilter</div>
  ),
  CustomFilterControl: ({ column }: { column: { id: string } }) => (
    <div data-testid={`column-filter-${column.id}`}>CustomFilter</div>
  ),
}));

vi.mock('@nvidia/foundations-react-core', () => ({
  Accordion: ({
    items,
  }: {
    items: Array<{
      value: string;
      slotTrigger: React.ReactNode;
      slotContent: React.ReactNode;
    }>;
  }) => (
    <div data-testid="accordion">
      {items.map((item) => (
        <div key={item.value} data-testid={`accordion-item-${item.value}`}>
          <div data-testid={`accordion-trigger-${item.value}`}>{item.slotTrigger}</div>
          <div data-testid={`accordion-content-${item.value}`}>{item.slotContent}</div>
        </div>
      ))}
    </div>
  ),
  Flex: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  Spinner: ({ description }: { description?: string }) => <div>{description}</div>,
}));

function makeFilterableColumn(
  id: string,
  filter: Record<string, unknown> | ReturnType<typeof dateTimeFilter>,
  opts: { filterValue?: unknown; header?: string } = {}
) {
  return {
    id,
    getCanFilter: () => true,
    getFilterValue: () => opts.filterValue,
    setFilterValue: vi.fn(),
    columnDef: {
      header: opts.header ?? id,
      meta: { filter },
    },
  };
}

describe('ColumnFilterPanel', () => {
  beforeEach(() => {
    mockColumns.length = 0;
  });

  it('returns null when no columns are filterable', () => {
    mockColumns.push({
      id: 'name',
      getCanFilter: () => false,
      columnDef: { header: 'Name', meta: {} },
    });

    const { container } = render(<ColumnFilterPanel />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders accordion items for each filterable column', () => {
    mockColumns.push(
      makeFilterableColumn('name', { type: 'text' }, { header: 'Name' }),
      makeFilterableColumn(
        'status',
        {
          type: 'single-select',
          options: [{ value: 'active', label: 'Active' }],
        },
        { header: 'Status' }
      )
    );

    render(<ColumnFilterPanel />);

    expect(screen.getByTestId('accordion-item-name')).toBeInTheDocument();
    expect(screen.getByTestId('accordion-item-status')).toBeInTheDocument();
    expect(screen.getByText('Name')).toBeInTheDocument();
    expect(screen.getByText('Status')).toBeInTheDocument();
  });

  it('renders DateTimeFilterControl for datetime filter', () => {
    mockColumns.push(
      makeFilterableColumn('created_at', dateTimeFilter('Created At'), { header: 'Created At' })
    );

    render(<ColumnFilterPanel />);

    expect(screen.getByTestId('column-filter-created_at')).toBeInTheDocument();
    expect(screen.getByText('DateTimeFilter')).toBeInTheDocument();
  });

  it('renders CustomFilterControl for non-datetime custom type', () => {
    mockColumns.push(
      makeFilterableColumn(
        'base_model',
        { type: 'custom', renderFilter: vi.fn() },
        { header: 'Base Model' }
      )
    );

    render(<ColumnFilterPanel />);

    expect(screen.getByTestId('column-filter-base_model')).toBeInTheDocument();
    expect(screen.getByText('CustomFilter')).toBeInTheDocument();
  });

  it('renders TextFilterControl for text filter type', () => {
    mockColumns.push(makeFilterableColumn('search', { type: 'text' }, { header: 'Search' }));

    render(<ColumnFilterPanel />);

    expect(screen.getByTestId('column-filter-search')).toBeInTheDocument();
    expect(screen.getByText('TextFilter')).toBeInTheDocument();
  });

  it('renders SingleSelectFilterControl for single-select filter type', () => {
    mockColumns.push(
      makeFilterableColumn(
        'status',
        {
          type: 'single-select',
          options: [{ value: 'a', label: 'A' }],
        },
        { header: 'Status' }
      )
    );

    render(<ColumnFilterPanel />);

    expect(screen.getByTestId('column-filter-status')).toBeInTheDocument();
    expect(screen.getByText('SingleSelectFilter')).toBeInTheDocument();
  });

  it('renders Spinner when filter is loading', () => {
    mockColumns.push(
      makeFilterableColumn('name', { type: 'text', loading: true }, { header: 'Name' })
    );

    render(<ColumnFilterPanel />);

    expect(screen.getByText('Loading filters...')).toBeInTheDocument();
  });

  it('uses filter label when available, falls back to header', () => {
    mockColumns.push(
      makeFilterableColumn('col1', { type: 'text', label: 'Custom Label' }, { header: 'Header' }),
      makeFilterableColumn('col2', { type: 'text' }, { header: 'Fallback Header' })
    );

    render(<ColumnFilterPanel />);

    expect(screen.getByText('Custom Label')).toBeInTheDocument();
    expect(screen.getByText('Fallback Header')).toBeInTheDocument();
  });
});
