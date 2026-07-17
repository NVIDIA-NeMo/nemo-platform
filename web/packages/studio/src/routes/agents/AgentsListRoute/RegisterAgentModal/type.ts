// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FormModalProps } from '@nemo/common/src/components/FormModal';
import { z } from 'zod';

export const registerAgentFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  url: z.string().trim().min(1, 'Endpoint URL is required'),
});

export type RegisterAgentFormData = z.infer<typeof registerAgentFormSchema>;

export interface RegisterAgentModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
}
