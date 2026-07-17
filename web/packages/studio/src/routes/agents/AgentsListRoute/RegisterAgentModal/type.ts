// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FormModalProps } from '@nemo/common/src/components/FormModal';
import { z } from 'zod';

const isHttpUrl = (value: string): boolean => {
  try {
    const parsed = new URL(value);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
};

export const registerAgentFormSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  url: z
    .string()
    .trim()
    .min(1, 'Endpoint URL is required')
    .refine(isHttpUrl, 'Enter a valid http(s) URL, e.g. http://localhost:10000'),
});

export type RegisterAgentFormData = z.infer<typeof registerAgentFormSchema>;

export interface RegisterAgentModalProps extends Pick<FormModalProps, 'open' | 'onClose'> {
  workspace: string;
}
