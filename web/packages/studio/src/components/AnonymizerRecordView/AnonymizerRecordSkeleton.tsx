// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Stack } from '@nvidia/foundations-react-core';
import { RecordSection } from '@studio/components/AnonymizerRecordView/RecordSection';
import { StackedSkeleton } from '@studio/components/StackedSkeleton';
import type { FC } from 'react';

const SKELETON_LINES = 8;

const SkeletonBlock: FC = () => (
  <Stack gap="density-sm">
    <StackedSkeleton count={SKELETON_LINES} />
  </Stack>
);

interface AnonymizerRecordSkeletonProps {
  readonly outputHeading: string;
}

export const AnonymizerRecordSkeleton: FC<AnonymizerRecordSkeletonProps> = ({ outputHeading }) => (
  <Stack gap="density-2xl">
    <Flex align="start" gap="density-2xl">
      <RecordSection className="flex-1 min-w-0" heading="Original">
        <SkeletonBlock />
      </RecordSection>
      <RecordSection className="flex-1 min-w-0" heading={outputHeading}>
        <SkeletonBlock />
      </RecordSection>
    </Flex>
    <RecordSection heading="Replacement Map">
      <SkeletonBlock />
    </RecordSection>
  </Stack>
);
