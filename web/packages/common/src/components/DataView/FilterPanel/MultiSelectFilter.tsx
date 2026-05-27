// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  DataViewColumn,
  MultiState,
} from '@nemo/common/src/components/DataView/FilterPanel/types';
import { useMultiToggle } from '@nemo/common/src/components/DataView/FilterPanel/useMultiToggle';
import type { FilterItem } from '@nemo/common/src/components/DataView/internal';
import { Checkbox, Stack } from '@nvidia/foundations-react-core';

export function MultiSelectFilterControl({ column }: { column: DataViewColumn }) {
  const filter = column.columnDef.meta?.filter;
  const value = column.getFilterValue() as MultiState | undefined;
  const toggle = useMultiToggle(column);

  if (filter?.type !== 'multi-select') return null;

  const options: FilterItem[] | undefined = filter.options ?? filter.optionsBuilder?.(column);
  if (!options) return null;

  return (
    <Stack gap="density-md">
      {options.map((opt) => (
        <Checkbox
          key={opt.value}
          data-testid={`column-filter-${column.id}-${opt.value}`}
          checked={value?.[opt.value] ?? false}
          onCheckedChange={() => toggle(opt.value)}
          disabled={opt.disabled}
          slotLabel={opt.label ?? opt.value}
          attributes={{
            CheckboxInput: {
              id: `column-filter-${column.id}-${opt.value}`,
              'aria-label': opt.label ?? opt.value,
            },
            Label: { htmlFor: `column-filter-${column.id}-${opt.value}` },
          }}
        />
      ))}
    </Stack>
  );
}
