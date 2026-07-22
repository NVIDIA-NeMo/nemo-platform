// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Text } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

interface IntakePayloadPreviewCellProps {
  value?: string;
  emptyValue?: string;
}

export const IntakePayloadPreviewCell: FC<IntakePayloadPreviewCellProps> = ({
  value,
  emptyValue = '—',
}) =>
  value ? (
    <Text className="cursor-default line-clamp-2" title={value}>
      {value}
    </Text>
  ) : (
    <Text>{emptyValue}</Text>
  );
