// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FormModalProps } from '@nemo/common/src/components/FormModal';
import { z } from 'zod';

export const registerAgentFormSchema = z
  .object({
    mode: z.enum(['url', 'config']),
    name: z.string().min(1, 'Name is required'),
    description: z.string().optional(),
    url: z.string().optional(),
    configText: z.string().optional(),
  })
  .superRefine((v, ctx) => {
    if (v.mode === 'url' && !v.url?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['url'],
        message: 'Endpoint URL is required',
      });
    }
    if (v.mode === 'config' && !v.configText?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['configText'],
        message: 'Config is required',
      });
    }
  });

export type RegisterAgentFormData = z.infer<typeof registerAgentFormSchema>;

export interface RegisterAgentModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
}
