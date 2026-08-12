// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Text } from '@nvidia/foundations-react-core';
import classNames from 'classnames';
import type { FC } from 'react';

export interface ComparisonLegendItem {
  id: string;
  label: string;
  color: string;
  dashed?: boolean;
  hidden?: boolean;
}

interface Props {
  items: ComparisonLegendItem[];
  interactive?: boolean;
  justify?: 'center' | 'end';
  onToggle?: (id: string) => void;
  onHover?: (id: string | null) => void;
}

const DOT_SIZE = 10;
const DOT_RADIUS = 4;

export const ComparisonLegend: FC<Props> = ({
  items,
  interactive = true,
  justify = 'end',
  onToggle,
  onHover,
}) => (
  <Flex wrap="wrap" gap="density-md" justify={justify} align="center">
    {items.map((item) => (
      <button
        key={item.id}
        type="button"
        disabled={!interactive}
        aria-pressed={!item.hidden}
        className={classNames(
          'flex items-center gap-1.5 rounded px-1 py-0.5',
          interactive && 'cursor-pointer hover:bg-component-hover',
          item.hidden && 'opacity-40'
        )}
        onClick={() => onToggle?.(item.id)}
        onMouseEnter={() => onHover?.(item.id)}
        onMouseLeave={() => onHover?.(null)}
        onFocus={() => onHover?.(item.id)}
        onBlur={() => onHover?.(null)}
      >
        <svg width={DOT_SIZE} height={DOT_SIZE} aria-hidden focusable="false">
          {/* Dashed series get a hollow dot so the legend still distinguishes them. */}
          <circle
            cx={DOT_SIZE / 2}
            cy={DOT_SIZE / 2}
            r={item.dashed ? DOT_RADIUS - 0.75 : DOT_RADIUS}
            fill={item.dashed ? 'none' : item.color}
            stroke={item.dashed ? item.color : 'none'}
            strokeWidth={item.dashed ? 1.5 : 0}
          />
        </svg>
        <Text kind="label/regular/md" className="text-placeholder">
          {item.label}
        </Text>
      </button>
    ))}
  </Flex>
);
