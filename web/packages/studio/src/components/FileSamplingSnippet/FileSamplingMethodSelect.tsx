// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FileSampleMethod } from '@nemo/common/src/utils/sampleTextLines';
import { Flex, Select } from '@nvidia/foundations-react-core';
import classnames from 'classnames';
import type { FC } from 'react';

const SAMPLE_METHOD_ITEMS: { value: FileSampleMethod; children: string }[] = [
  { value: 'random', children: 'Random' },
  { value: 'head', children: 'Head' },
  { value: 'tail', children: 'Tail' },
];

const DEFAULT_SELECT_CLASS = 'w-[110px] grow-0';
const COUNT_PRESETS = [5, 10, 25, 50, 100] as const;

function buildCountItems(maxRows: number, current: number): { value: string; children: string }[] {
  const cap = Math.max(1, maxRows);
  const set = new Set<number>();
  for (const p of COUNT_PRESETS) {
    if (p <= cap) set.add(p);
  }
  set.add(Math.min(current, cap));
  set.add(cap);
  return [...set]
    .filter((n) => n >= 1 && n <= cap)
    .sort((a, b) => a - b)
    .map((n) => ({ value: String(n), children: String(n) }));
}

function clampRowCount(value: number, maxRows: number): number {
  return Math.min(Math.max(1, value), Math.max(1, maxRows));
}

export interface FileSamplingMethodSelectAttributes {
  /** Styling and interaction options for the underlying single-select. */
  select?: {
    className?: string;
    disabled?: boolean;
  };
}

/** When set, the row-count select is shown next to the method inside one grouped control. */
export interface FileSamplingRowCountGroup {
  value: number;
  onValueChange: (n: number) => void;
  /** Dataset row count. Caps presets and the count select. */
  maxRows: number;
  disabled?: boolean;
}

export interface FileSamplingMethodSelectProps {
  value: FileSampleMethod;
  onValueChange: (method: FileSampleMethod) => void;
  attributes?: FileSamplingMethodSelectAttributes;
  /** Renders method + "max rows" select in one grouped control. */
  rowCountGroup?: FileSamplingRowCountGroup;
  /** Size of the underlying selects. Defaults to 'small'. */
  size?: 'small' | 'medium' | 'large';
}

export const FileSamplingMethodSelect: FC<FileSamplingMethodSelectProps> = ({
  value,
  onValueChange,
  attributes,
  rowCountGroup,
  size = 'small',
}) => {
  const selectAttrs = attributes?.select ?? {};

  const methodSelect = (
    <Select
      multiple={false}
      items={SAMPLE_METHOD_ITEMS}
      value={value}
      onValueChange={(next) => onValueChange(next as FileSampleMethod)}
      disabled={selectAttrs.disabled}
      size={size}
      className={classnames(DEFAULT_SELECT_CLASS, selectAttrs.className)}
    />
  );

  if (!rowCountGroup) {
    return methodSelect;
  }

  const countItems = buildCountItems(rowCountGroup.maxRows, rowCountGroup.value);
  const countValue = String(clampRowCount(rowCountGroup.value, rowCountGroup.maxRows));

  return (
    <Flex role="group" gap="density-sm" align="center" aria-label="File sampling">
      {methodSelect}
      <Select
        multiple={false}
        items={countItems}
        value={countValue}
        onValueChange={(next) => rowCountGroup.onValueChange(Number(next))}
        disabled={selectAttrs.disabled || rowCountGroup.disabled}
        size={size}
        className="w-[72px] grow-0"
      />
    </Flex>
  );
};
