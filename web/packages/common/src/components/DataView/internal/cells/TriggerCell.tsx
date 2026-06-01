// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CellContext } from '@tanstack/react-table';
import type { JSX, ReactNode } from 'react';

export type MakeTriggerCellProps<TData> =
  | {
      onSelect: (data: TData, ctx: CellContext<TData, unknown>) => void;
      link?: never;
    }
  | {
      onSelect?: never;
      link: (props: { children: ReactNode; data: TData }) => ReactNode;
    };

/**
 * Generates a cell for triggering an action or navigating to a page. Accepts either an
 * `onSelect` function or a `link` component.
 */
export function makeTriggerCell<TData, TValue = unknown>({
  link: LinkComponent,
  onSelect,
}: MakeTriggerCellProps<TData>): (cellContext: CellContext<TData, TValue>) => JSX.Element {
  const TriggerCell = (cellContext: CellContext<TData, TValue>) => {
    const data = cellContext.row.original;
    const value = cellContext.getValue() as ReactNode;
    return LinkComponent ? (
      <span className="cursor-pointer underline [&_a]:text-inherit">
        <LinkComponent data={data}>{value}</LinkComponent>
      </span>
    ) : (
      <button
        className="font-inherit max-w-full cursor-pointer truncate border-none bg-inherit p-0 text-inherit underline"
        onClick={() => onSelect!(data, cellContext)}
        type="button"
      >
        {value}
      </button>
    );
  };
  return TriggerCell;
}
