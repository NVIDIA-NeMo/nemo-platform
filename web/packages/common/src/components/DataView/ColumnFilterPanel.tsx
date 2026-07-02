// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { isDateTimeFilter } from '@nemo/common/src/components/DataView/dateTimeFilter';
import {
  TextFilterControl,
  BooleanFilterControl,
  SingleSelectFilterControl,
  MultiSelectFilterControl,
  DateTimeFilterControl,
  NumberRangeFilterControl,
  CustomFilterControl,
} from '@nemo/common/src/components/DataView/FilterPanel';
import { isNumberRangeFilter } from '@nemo/common/src/components/DataView/FilterPanel/NumberRangeFilter/util';
import type { DataViewColumn } from '@nemo/common/src/components/DataView/FilterPanel/types';
import { useInnerDataViewContext } from '@nemo/common/src/components/DataView/internal';
import { Accordion, Flex, Spinner } from '@nvidia/foundations-react-core';

type ColumnFilterMeta = NonNullable<NonNullable<DataViewColumn['columnDef']['meta']>['filter']>;

export interface ColumnFilterPanelProps {
  /** Accordion items expanded by default. Defaults to all filterable column ids. */
  defaultExpanded?: string[];
}

/**
 * Renders column filter definitions as an Accordion panel.
 *
 * Must be rendered inside a `DataView.Root`. Reads filterable columns from
 * the DataView table context (columns with `meta.filter` defined), then
 * renders each as an expandable Accordion section with the appropriate
 * control (TextInput, Select, Checkbox list, Switch toggles, or custom).
 *
 * Filter state is managed through the DataView column filtering state
 * (`column.getFilterValue()` / `column.setFilterValue()`), so changes
 * are automatically reflected in `DataView.AppliedFilters`.
 */
export const ColumnFilterPanel = ({ defaultExpanded }: ColumnFilterPanelProps) => {
  const { table } = useInnerDataViewContext();
  const filterableColumns = table.getAllLeafColumns().filter((col) => col.getCanFilter());

  if (filterableColumns.length === 0) return null;

  const expandedIds = defaultExpanded ?? filterableColumns.map((col) => col.id);

  // Map of filter types to their respective control components
  const filterMap: Record<
    ColumnFilterMeta['type'],
    (column: DataViewColumn, filter: ColumnFilterMeta) => React.ReactNode
  > = {
    text: (column) => <TextFilterControl column={column} />,
    boolean: (column) => <BooleanFilterControl column={column} />,
    'single-select': (column) => <SingleSelectFilterControl column={column} />,
    'multi-select': (column) => <MultiSelectFilterControl column={column} />,
    custom: (column, filter) =>
      isDateTimeFilter(filter) ? (
        <DateTimeFilterControl column={column} />
      ) : isNumberRangeFilter(filter) ? (
        <NumberRangeFilterControl column={column} />
      ) : (
        <CustomFilterControl column={column} />
      ),
  };

  const getFilterLabel = (column: DataViewColumn): string => {
    const filter = column.columnDef.meta?.filter;
    const header = column.columnDef.header;
    return filter?.label ?? (typeof header === 'string' ? header : column.id);
  };

  const getSlotContent = (column: DataViewColumn): React.ReactNode => {
    const filter = column.columnDef.meta?.filter;
    if (!filter) return null;
    if (filter.loading) return <Spinner description="Loading filters..." size="small" />;
    return filterMap[filter.type]?.(column, filter) ?? null;
  };

  return (
    <Accordion
      defaultValue={expandedIds}
      multiple
      items={filterableColumns.map((column) => ({
        value: column.id,
        slotTrigger: (
          <Flex align="center" gap="2">
            {getFilterLabel(column)}
          </Flex>
        ),
        slotContent: getSlotContent(column),
      }))}
    />
  );
};
