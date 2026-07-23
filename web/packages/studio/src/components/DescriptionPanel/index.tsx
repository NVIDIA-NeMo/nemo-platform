// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Card, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { type FC, type ReactNode } from 'react';

interface DescriptionPanelProps {
  title: string;
  description: string;
  slotTitleEnd?: ReactNode;
}

/** Fixed-height, scrollable card used for the insight, evaluation, and summary descriptions. */
export const DescriptionPanel: FC<DescriptionPanelProps> = ({
  title,
  description,
  slotTitleEnd,
}) => (
  <Card className="min-w-0 flex-1 basis-0">
    <Stack className="min-w-0 gap-density-sm">
      <Flex className="min-h-8 items-center justify-between gap-density-sm">
        <Text kind="title/sm">{title}</Text>
        {slotTitleEnd}
      </Flex>
      <div tabIndex={0} role="group" aria-label={title} className="h-40 overflow-y-auto">
        <Text kind="body/regular/md">{description}</Text>
      </div>
    </Stack>
  </Card>
);
