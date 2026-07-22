// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { parse } from 'yaml';
import { z } from 'zod';

export const REGISTRATION_TYPE_NAT = 'nat';
export const REGISTRATION_TYPE_EXTERNAL = 'external';

const parseWorkflowConfig = (source: string): Record<string, unknown> | null => {
  try {
    const value: unknown = parse(source);
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    return value as Record<string, unknown>;
  } catch {
    return null;
  }
};

export const registerAgentSchema = z
  .object({
    registrationType: z.enum([REGISTRATION_TYPE_NAT, REGISTRATION_TYPE_EXTERNAL]),
    name: z
      .string()
      .trim()
      .min(1, 'Name is required')
      .regex(/^[a-zA-Z0-9_.-]+$/, 'Use only letters, digits, dots, hyphens, and underscores'),
    description: z.string(),
    workflowConfig: z.string(),
    endpointUrl: z.string(),
  })
  .superRefine((data, ctx) => {
    if (data.registrationType === REGISTRATION_TYPE_NAT) {
      if (!data.workflowConfig.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Workflow YAML is required',
          path: ['workflowConfig'],
        });
      } else if (parseWorkflowConfig(data.workflowConfig) === null) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Enter a valid YAML object',
          path: ['workflowConfig'],
        });
      }
      return;
    }

    try {
      const url = new URL(data.endpointUrl);
      if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new Error('protocol');
    } catch {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Enter a valid HTTP or HTTPS endpoint URL',
        path: ['endpointUrl'],
      });
    }
  });

export type RegisterAgentFormData = z.infer<typeof registerAgentSchema>;

export const workflowConfigFromForm = (source: string): Record<string, unknown> => {
  const config = parseWorkflowConfig(source);
  if (!config) throw new Error('Workflow YAML must contain an object');
  return config;
};
