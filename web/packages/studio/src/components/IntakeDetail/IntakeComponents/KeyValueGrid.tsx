// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import type { FC, ReactNode } from 'react';

export interface KeyValueGridItem {
  key: string;
  label: string;
  value: ReactNode;
  wrapValue?: boolean;
}

const isPresentValue = (value: ReactNode): boolean =>
  value !== null && value !== undefined && value !== '';

const KEY_VALUE_GRID_CLASS = 'flex flex-wrap min-w-0 gap-x-density-2xl gap-y-density-lg';

/**
 * Key/value fields laid out in a wrapping flow: each pair takes only the width
 * it needs and wraps to the next line as the row fills, with the gap providing
 * consistent spacing. Skips empty values, and renders nothing when no field has
 * a value.
 */
export const KeyValueGrid: FC<{ items: readonly KeyValueGridItem[] }> = ({ items }) => {
  const visible = items.filter((item) => isPresentValue(item.value));
  if (visible.length === 0) {
    return null;
  }
  return (
    <div className={KEY_VALUE_GRID_CLASS}>
      {visible.map((item) => (
        <KVPair
          key={item.key}
          label={item.label}
          value={item.value}
          orientation="vertical"
          attributes={
            item.wrapValue
              ? {
                  value: {
                    className: 'min-w-0 break-all text-wrap',
                  },
                }
              : undefined
          }
        />
      ))}
    </div>
  );
};
