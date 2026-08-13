// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Skeleton, Stack } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

interface Props {
  height: number;
}

export const ComparisonLineChartSkeleton: FC<Props> = ({ height }) => (
  <Stack gap="density-sm" className="w-full" data-testid="comparison-line-chart-skeleton">
    {/* eslint-disable-next-line no-restricted-syntax */}
    <div className="w-full" style={{ height }}>
      <Skeleton className="w-full h-full" />
    </div>
    <Flex justify="center" gap="density-md">
      {[0, 1, 2].map((index) => (
        <Skeleton key={index} className="w-20 h-[20px]" />
      ))}
    </Flex>
  </Stack>
);
