// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Panel, Stack, Text } from '@nvidia/foundations-react-core';
import { FC } from 'react';

export interface StatTileProps {
  label: string;
  value: string;
  hint?: string;
  hintStatus?: 'success' | 'warning' | 'error' | 'neutral';
}

const MUTED_CLASS_NAME = 'text-placeholder';

const HINT_STATUS_CLASS_NAME: Record<NonNullable<StatTileProps['hintStatus']>, string> = {
  success: 'text-[color:var(--text-color-feedback-success)]',
  warning: 'text-[color:var(--text-color-feedback-warning)]',
  error: 'text-[color:var(--text-color-feedback-danger)]',
  neutral: MUTED_CLASS_NAME,
};

export const StatTile: FC<StatTileProps> = ({ label, value, hint, hintStatus }) => (
  <Panel className="max-w-sm">
    <Stack gap="density-sm">
      <Text kind="body/regular/sm" className={MUTED_CLASS_NAME}>
        {label}
      </Text>
      <Text kind="label/bold/2xl">{value}</Text>
      {hint ? (
        <Text kind="body/regular/sm" className={HINT_STATUS_CLASS_NAME[hintStatus ?? 'neutral']}>
          {hint}
        </Text>
      ) : null}
    </Stack>
  </Panel>
);
