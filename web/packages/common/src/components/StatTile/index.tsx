// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import cn from 'classnames';
import type { FC } from 'react';

export type StatTileStatus = 'success' | 'warning' | 'error' | 'neutral';

/**
 * `default` is the diagnostics tile: compact label, hint line, capped width.
 * `metric` is the overview tile: larger label, the trailing label reads as a
 * unit sitting on the value's baseline, and the tile fills its grid column.
 */
export type StatTileVariant = 'default' | 'metric';

export interface StatTileProps {
  label: string;
  value: string;
  trailingLabel?: string;
  trailingLabelStatus?: StatTileStatus;
  hint?: string;
  hintStatus?: StatTileStatus;
  className?: string;
  bordered?: boolean;
  variant?: StatTileVariant;
}

const MUTED_CLASS_NAME = 'text-placeholder';

const STATUS_CLASS_NAME: Record<StatTileStatus, string> = {
  success: 'text-[color:var(--text-color-feedback-success)]',
  warning: 'text-[color:var(--text-color-feedback-warning)]',
  error: 'text-[color:var(--text-color-feedback-danger)]',
  neutral: MUTED_CLASS_NAME,
};

export const StatTile: FC<StatTileProps> = ({
  label,
  value,
  trailingLabel,
  trailingLabelStatus,
  hint,
  hintStatus,
  className,
  bordered = true,
  variant = 'default',
}) => {
  const isMetric = variant === 'metric';
  const neutralClassName = isMetric ? 'text-secondary' : MUTED_CLASS_NAME;
  const statusClassName = (status: StatTileStatus | undefined) =>
    status && status !== 'neutral' ? STATUS_CLASS_NAME[status] : neutralClassName;

  const content = (
    <Stack gap={isMetric ? 'density-xxs' : 'density-sm'}>
      <Text kind={isMetric ? 'body/regular/md' : 'body/regular/sm'} className={neutralClassName}>
        {label}
      </Text>
      <Flex
        align={isMetric ? 'end' : 'baseline'}
        gap={isMetric ? 'density-md' : 'density-sm'}
        wrap="wrap"
      >
        <Text kind="label/bold/2xl" className="tabular-nums">
          {value}
        </Text>
        {trailingLabel ? (
          <Text
            kind="body/regular/sm"
            className={cn(statusClassName(trailingLabelStatus), isMetric && 'pb-density-xs')}
          >
            {trailingLabel}
          </Text>
        ) : null}
      </Flex>
      {hint ? (
        <Text kind="body/regular/sm" className={statusClassName(hintStatus)}>
          {hint}
        </Text>
      ) : null}
    </Stack>
  );

  if (!bordered) {
    return content;
  }

  return (
    <Panel
      className={cn(isMetric ? 'w-full' : 'max-w-sm', className)}
      elevation="high"
      data-testid="stat-tile-surface"
    >
      {content}
    </Panel>
  );
};
