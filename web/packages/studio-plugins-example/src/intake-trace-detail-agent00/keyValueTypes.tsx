// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack, Text } from '@nvidia/foundations-react-core';
import type { FC, ReactNode } from 'react';

export interface HighlightMetric {
  readonly id: string;
  readonly label: string;
  readonly value: ReactNode;
}

export const HighlightMetricItem: FC<{ label: string; value: ReactNode }> = ({ label, value }) => (
  <Stack gap="density-xs" className="w-max shrink-0">
    <Text kind="label/regular/md" className="whitespace-nowrap text-secondary">
      {label}
    </Text>
    {typeof value === 'string' ? (
      <Text kind="title/bold/lg" className="whitespace-nowrap text-primary">
        {value}
      </Text>
    ) : (
      value
    )}
  </Stack>
);

export interface KeyValueEntry {
  readonly id: string;
  readonly label: string;
  readonly value: ReactNode;
  readonly wrapValue?: boolean;
}
