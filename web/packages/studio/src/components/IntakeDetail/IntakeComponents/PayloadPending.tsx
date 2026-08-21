// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, Spinner } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

/** Placeholder while a payload is too large to render immediately, or its renderer is loading. */
export const PayloadPending: FC = () => (
  <Flex
    align="center"
    justify="center"
    className="min-h-[160px] rounded-md border border-base bg-surface-raised p-density-xl"
  >
    <Spinner size="medium" aria-label="Rendering payload" />
  </Flex>
);
