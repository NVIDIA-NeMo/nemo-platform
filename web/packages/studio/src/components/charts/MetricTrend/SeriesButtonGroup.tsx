// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, Flex } from '@nvidia/foundations-react-core';
import type { MetricTrendSeries } from '@studio/components/charts/MetricTrend';
import type { FC } from 'react';

interface Props {
  series: MetricTrendSeries[];
  activeId?: string;
  /** Names the group for screen readers — whatever the trend is measuring. */
  label: string;
  onSelect: (seriesId: string) => void;
}

/**
 * Picks which evaluator the trendline plots.
 *
 * Tiny buttons rather than `Tag`: these are actions, not metadata, and `Tag`'s selected
 * styling reads as a filter chip. The selected one promotes to the brand primary kind, so
 * the design system supplies the green fill and a foreground that contrasts with it —
 * rather than this component forcing colors past the design system's own button CSS.
 */
export const SeriesButtonGroup: FC<Props> = ({ series, activeId, label, onSelect }) => (
  <Flex align="center" gap="density-sm" wrap="wrap" role="group" aria-label={label}>
    {series.map((s) => {
      const isActive = s.id === activeId;
      return (
        <Button
          key={s.id}
          kind={isActive ? 'primary' : 'tertiary'}
          color={isActive ? 'brand' : undefined}
          size="tiny"
          aria-pressed={isActive}
          // Stop the click here: a trend can sit inside a card that navigates on click, and
          // picking a series should switch the chart rather than follow the card.
          onClick={(e) => {
            e.stopPropagation();
            onSelect(s.id);
          }}
        >
          {s.label}
        </Button>
      );
    })}
  </Flex>
);
