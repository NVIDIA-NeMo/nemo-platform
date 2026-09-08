// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useInnerDataViewContext } from '@nemo/common/src/components/DataView/internal/context';
import type { IntentionalAny } from '@nemo/common/src/components/DataView/internal/types';
import { getHeaderId } from '@nemo/common/src/components/DataView/internal/utils/header-utils';
import type { Column, ColumnSizingState, Header } from '@tanstack/react-table';
import type { CSSProperties, MouseEvent, TouchEvent } from 'react';

/** Backslash-escape everything that is not valid unescaped in a CSS identifier, so a column id can
 * be named inside a `var()` reference. Only characters outside `[A-Za-z0-9_-]` are touched, which
 * keeps hex digits — the one class where `\x` would start a numeric escape rather than a literal —
 * out of it. The escape is what CSS parsing resolves away, so the reference still names the same
 * property `getColumnWidths` declared under the raw id. */
const escapeCssIdentifier = (id: string): string => id.replace(/[^\w-]/g, (char) => `\\${char}`);

/**
 * The `width` value a column's cells are sized by, read from the custom property that
 * {@link getColumnWidths} sets on the table.
 *
 * The id is escaped because the two sides are handled differently by the browser: `getColumnWidths`
 * declares the property through the CSSOM, which stores whatever name it is handed, while this is
 * parsed as CSS — where an unescaped `.` or `:` in the name makes the whole declaration invalid and
 * drops it. A dropped width leaves that cell to size to its own content, and because a header and
 * its body cells hold different content, they end up different widths; the flex row then
 * redistributes the slack across every *other* column too, so one bad id shifts the whole table's
 * headers out from over their data. Column ids routinely carry those characters — an evaluator
 * column is named for its metric, e.g. `evaluator-llm-judge.answers_question`.
 */
export function getColumnWidth(id: string): string {
  const variable = `--col-${escapeCssIdentifier(id)}-size`;
  return `calc(var(${variable}) * 1px)`;
}

export function isColumnAutoSized(
  column: Column<IntentionalAny>,
  columnSizing: ColumnSizingState
): boolean {
  return !columnSizing[column.id] && !column.columnDef.meta?._isSizeInitialized;
}

export function getCellStyle({
  column,
  disableAutoSizing,
}: {
  column: Column<IntentionalAny>;
  disableAutoSizing: boolean;
}): CSSProperties {
  const width = disableAutoSizing ? column.getSize() : getColumnWidth(column.id);
  const cellStyle: CSSProperties = {
    minWidth: width,
    width,
    maxWidth: width,
  };
  if (column.getIsPinned() === 'left') {
    cellStyle.left = column.getStart('left');
  } else if (column.getIsPinned() === 'right') {
    cellStyle.right = column.getAfter('right');
  }
  return cellStyle;
}

export function getColumnWidths({
  columnSizing,
  columns,
  disableAutoSizing,
}: {
  columnSizing: ColumnSizingState;
  columns: Column<IntentionalAny>[];
  disableAutoSizing: boolean;
}): Record<string, string | number> {
  const colSizes: Record<string, string | number> = {};
  columns.forEach((column) => {
    const shouldUseTableSize = disableAutoSizing || !isColumnAutoSized(column, columnSizing);
    // Declared under the raw id: React sets custom properties through the CSSOM, which takes the
    // name literally. `getColumnWidth` escapes its `var()` reference back to this same name.
    colSizes[`--col-${column.id}-size`] = shouldUseTableSize ? column.getSize() : 'auto';
  });
  return colSizes;
}

export function useHandleResize(header: Header<IntentionalAny, unknown>) {
  const { table } = useInnerDataViewContext();
  return {
    handleResize: (event: MouseEvent | TouchEvent) => {
      const isAutoSizedColumn = isColumnAutoSized(header.column, table.getState().columnSizing);
      if (isAutoSizedColumn) {
        const element = document.getElementById(getHeaderId(header.id));
        const elementWidth = element?.getBoundingClientRect().width;
        if (elementWidth) {
          table.setColumnSizing((columnSizingInfo) => {
            columnSizingInfo[header.id] = elementWidth;
            return columnSizingInfo;
          });
        }
      }
      const handler = header.getResizeHandler();
      handler(event);
    },
    handleDoubleClick: () => {
      header.column.resetSize();
    },
  };
}
