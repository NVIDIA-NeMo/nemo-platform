// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

export type StatTileStatus = 'success' | 'warning' | 'error' | 'neutral';

export interface StatTileProps {
  label: string;
  value: string;
  trailingLabel?: string;
  trailingLabelStatus?: StatTileStatus;
  hint?: string;
  hintStatus?: StatTileStatus;
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
}) => (
  <Panel className="max-w-sm">
    <Stack gap="density-sm">
      <Text kind="body/regular/sm" className={MUTED_CLASS_NAME}>
        {label}
      </Text>
      <Flex align="baseline" gap="density-sm" wrap="wrap">
        <Text kind="label/bold/2xl">{value}</Text>
        {trailingLabel ? (
          <Text
            kind="body/regular/sm"
            className={STATUS_CLASS_NAME[trailingLabelStatus ?? 'neutral']}
          >
            {trailingLabel}
          </Text>
        ) : null}
      </Flex>
      {hint ? (
        <Text kind="body/regular/sm" className={STATUS_CLASS_NAME[hintStatus ?? 'neutral']}>
          {hint}
        </Text>
      ) : null}
    </Stack>
  </Panel>
);
