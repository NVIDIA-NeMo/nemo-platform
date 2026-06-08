// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { DataViewColumn } from '@nemo/common/src/components/DataView/FilterPanel/types';
import { DEFAULT_DEBOUNCE_MS } from '@nemo/common/src/constants';
import { TextInput } from '@nvidia/foundations-react-core';
import { useEffect, useState } from 'react';
import { useDebouncedCallback } from 'use-debounce';

export function TextFilterControl({ column }: { column: DataViewColumn }) {
  const filter = column.columnDef.meta?.filter;
  const committedValue = column.getFilterValue() as string | undefined;
  const [localValue, setLocalValue] = useState(committedValue ?? '');

  // Keep local state in sync when the committed filter value changes externally
  // (e.g. "Clear Filters" resets it to undefined).
  useEffect(() => {
    setLocalValue(committedValue ?? '');
  }, [committedValue]);

  const commitFilter = useDebouncedCallback((v: string) => {
    column.setFilterValue(v || undefined);
  }, DEFAULT_DEBOUNCE_MS);

  const handleChange = (v: string) => {
    setLocalValue(v);
    commitFilter(v);
  };

  return (
    <TextInput
      data-testid={`column-filter-${column.id}`}
      placeholder={(filter?.type === 'text' && filter.placeholder) || 'Filter'}
      value={localValue}
      onValueChange={handleChange}
      dismissible
      size="medium"
    />
  );
}
