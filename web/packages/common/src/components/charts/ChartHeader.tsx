// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Text } from '@nvidia/foundations-react-core';
import type { FC, ReactNode } from 'react';

interface Props {
  title?: ReactNode;
  legend?: ReactNode;
}

/** Title on the left, legend on the right; renders when either is present. */
export const ChartHeader: FC<Props> = ({ title, legend }) =>
  title || legend ? (
    <Flex justify={title ? 'between' : 'end'} align="center" gap="density-md" className="pb-2">
      {title && <Text kind="label/bold/lg">{title}</Text>}
      {legend}
    </Flex>
  ) : null;
