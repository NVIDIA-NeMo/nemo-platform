// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ChartSwatch } from '@nemo/common/src/components/charts/ChartSwatch';
import type { ChartLegendItem } from '@nemo/common/src/components/charts/types';
import { Button, Flex, Text } from '@nvidia/foundations-react-core';
import classNames from 'classnames';
import type { FC } from 'react';

interface Props {
  items: ChartLegendItem[];
  interactive?: boolean;
  justify?: 'center' | 'end';
  onToggle?: (id: string) => void;
  onHover?: (id: string | null) => void;
}

export const ChartLegend: FC<Props> = ({
  items,
  interactive = true,
  justify = 'end',
  onToggle,
  onHover,
}) => (
  <Flex wrap="wrap" gap="density-md" justify={justify} align="center">
    {items.map((item) => (
      <Button
        key={item.id}
        kind="tertiary"
        size="tiny"
        disabled={!interactive}
        aria-pressed={!item.hidden}
        className={classNames('gap-1.5', item.hidden && 'opacity-40')}
        onClick={() => onToggle?.(item.id)}
        onMouseEnter={() => onHover?.(item.id)}
        onMouseLeave={() => onHover?.(null)}
        onFocus={() => onHover?.(item.id)}
        onBlur={() => onHover?.(null)}
      >
        <ChartSwatch color={item.color} dashed={item.dashed} />
        <Text kind="label/regular/md" className="text-placeholder">
          {item.label}
        </Text>
      </Button>
    ))}
  </Flex>
);
