// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DataViewColumn } from '@nemo/common/src/components/DataView/FilterPanel/types';
import { DebouncedTextInput } from '@nemo/common/src/components/DataView/internal/DebouncedTextInput';

export function TextFilterControl({ column }: { column: DataViewColumn }) {
  const filter = column.columnDef.meta?.filter;
  const committedValue = column.getFilterValue() as string | undefined;

  return (
    <DebouncedTextInput
      data-testid={`column-filter-${column.id}`}
      placeholder={(filter?.type === 'text' && filter.placeholder) || 'Filter'}
      value={committedValue ?? ''}
      onValueChange={(v) => column.setFilterValue(v || undefined)}
      dismissible
      size="medium"
    />
  );
}
