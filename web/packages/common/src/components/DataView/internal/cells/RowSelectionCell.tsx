// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useInnerDataViewContext } from '@nemo/common/src/components/DataView/internal/context';
import { Checkbox, type CheckboxProps } from '@nvidia/foundations-react-core';
import type { CellContext, HeaderContext } from '@tanstack/react-table';
import type { JSX } from 'react';

/**
 * A cell component for the row selection column. Renders the row selection checkbox.
 * Disabled if the row is not selectable.
 */
export function RowSelectionCell<TData>({
  ctx,
  ...props
}: { ctx: CellContext<TData, unknown> } & CheckboxProps): JSX.Element {
  const { isDataViewLoadingState, isDataViewEmptyState, isDataViewErrorState } =
    useInnerDataViewContext();
  const canSelect = ctx.row.getCanSelect();
  const isSelected = ctx.row.getIsSelected();
  const getIsSomeRowsSelected = ctx.row.getIsSomeSelected();
  return (
    <Checkbox
      attributes={{
        CheckboxInput: { 'aria-label': isSelected ? 'Deselect row' : 'Select row' },
      }}
      checked={getIsSomeRowsSelected ? 'indeterminate' : isSelected}
      data-selected={isSelected}
      data-has-selected-rows={getIsSomeRowsSelected}
      disabled={
        isDataViewLoadingState || isDataViewEmptyState || isDataViewErrorState || !canSelect
      }
      onCheckedChange={ctx.row.getToggleSelectedHandler()}
      {...props}
    />
  );
}

/** A header cell component for the row selection column. Renders the global selection checkbox. */
export function RowSelectionHeaderCell<TData>({
  ctx,
  ...props
}: { ctx: HeaderContext<TData, unknown> } & CheckboxProps): JSX.Element {
  const { isDataViewLoadingState, isDataViewEmptyState, isDataViewErrorState } =
    useInnerDataViewContext();
  const isAllRowsSelected = ctx.table.getIsAllRowsSelected();
  const isSomeRowsSelected = ctx.table.getIsSomeRowsSelected();
  return (
    <Checkbox
      attributes={{
        CheckboxInput: {
          'aria-label': isAllRowsSelected ? 'Deselect all rows' : 'Select all rows',
        },
      }}
      checked={isAllRowsSelected || (isSomeRowsSelected && 'indeterminate')}
      disabled={isDataViewLoadingState || isDataViewEmptyState || isDataViewErrorState}
      onCheckedChange={(c) => {
        ctx.table.toggleAllRowsSelected(c === 'indeterminate' ? false : c);
      }}
      {...props}
    />
  );
}
