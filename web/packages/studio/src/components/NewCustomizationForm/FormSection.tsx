// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Stack, Text } from '@nvidia/foundations-react-core';
import type { FC, ReactNode } from 'react';

interface FormSectionProps {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}

export const FormSection: FC<FormSectionProps> = ({ title, description, children }) => (
  <Stack gap="density-md">
    <Stack gap="density-sm" className="pb-density-xl">
      <Text kind="body/bold/lg">{title}</Text>
      {description && <Text kind="body/regular/md">{description}</Text>}
    </Stack>
    {children}
  </Stack>
);
