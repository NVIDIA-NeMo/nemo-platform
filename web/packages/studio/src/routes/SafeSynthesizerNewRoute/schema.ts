// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import type { SafeSynthesizerJobRequest } from '@nemo/sdk/generated/safe-synthesizer/schema';
import { MAX_NUM_RECORDS } from '@studio/routes/SafeSynthesizerNewRoute/constants';
import { z } from 'zod';

export const safeSynthesizerJobRequestSchema = z.object({
  name: z.string().optional(),
  description: z.string().optional(),
  namespace: z.string().optional(),
  spec: z.object({
    data_source: z
      .string()
      .min(1, 'Data source is required')
      .refine((val) => {
        const hashIdx = val.indexOf('#');
        if (hashIdx === -1 || hashIdx !== val.lastIndexOf('#')) return false;
        const filesetPart = val.slice(0, hashIdx);
        const filePath = val.slice(hashIdx + 1);
        const slashIdx = filesetPart.indexOf('/');
        if (slashIdx === -1) return false;
        const workspace = filesetPart.slice(0, slashIdx);
        const name = filesetPart.slice(slashIdx + 1);
        return (
          workspace.length > 0 && name.length > 0 && !name.includes('/') && filePath.length > 0
        );
      }, 'Data source must be a valid fileset reference (workspace/name#path)'),
    config: z.object({
      data: z
        .object({
          group_training_examples_by: z.string().optional(),
          order_training_examples_by: z.string().optional(),
        })
        .optional()
        .refine(
          (data) => {
            if (!data) return true;
            const hasOrderBy =
              data.order_training_examples_by && data.order_training_examples_by.trim() !== '';
            if (hasOrderBy) {
              return (
                data.group_training_examples_by && data.group_training_examples_by.trim() !== ''
              );
            }
            return true;
          },
          {
            message:
              'group_training_examples_by is required when order_training_examples_by is set',
            path: ['group_training_examples_by'],
          }
        ),
      enable_synthesis: z.boolean().optional(),
      enable_replace_pii: z.boolean().optional(),
      training: z
        .object({
          num_input_records_to_sample: z
            .any()
            .refine(
              (val) => {
                // If it's 'auto', it's valid
                if (val === 'auto') return true;
                // If it's a blank string or whitespace, it's invalid
                if (val === '' || (typeof val === 'string' && val.trim() === '')) return false;
                // If it's a number, validate it
                return typeof val === 'number';
              },
              {
                message: 'Number of input records is required',
              }
            )
            .refine(
              (val) => {
                // If it's 'auto', skip number validation
                if (val === 'auto') return true;
                // If it's a number, validate it
                if (typeof val === 'number') {
                  return Number.isInteger(val) && val > 0;
                }
                return true;
              },
              {
                message: 'Must be a positive whole number',
              }
            )
            .refine(
              (val) => {
                // If it's 'auto', skip max validation
                if (val === 'auto') return true;
                // If it's a number, validate it's not too large
                if (typeof val === 'number') {
                  return val <= Number.MAX_SAFE_INTEGER;
                }
                return true;
              },
              {
                message: `Must be less than or equal to ${Number.MAX_SAFE_INTEGER}`,
              }
            ),
          rope_scaling_factor: z.union([z.literal('auto'), z.number().int().min(1).max(6)]),
        })
        .optional(),
      generation: z
        .object({
          num_records: z
            .any()
            .refine((val) => {
              // Handle blank string case
              return !(val === '' || (typeof val === 'string' && val.trim() === ''));
            }, 'Number of records is required')
            .refine((val) => {
              // Convert to number and validate
              const num = Number(val);
              return !isNaN(num);
            }, 'Must be a number')
            .transform((val) => Number(val))
            .refine((val) => Number.isInteger(val), 'Must be a whole number')
            .refine((val) => val > 0, 'Must be greater than 0')
            .refine((val) => val <= MAX_NUM_RECORDS, 'Must be less than or equal to 130,000'),
          temperature: z.number().min(0).max(2).optional(),
          top_p: z.number().min(0).max(1).optional(),
          repetition_penalty: z.number().min(1).optional(),
        })
        .optional(),
      privacy: z
        .object({
          dp_enabled: z.boolean().optional(),
        })
        .optional(),
    }),
  }),
}) satisfies z.ZodType<SafeSynthesizerJobRequest>;

export type SafeSynthesizerFormData = z.infer<typeof safeSynthesizerJobRequestSchema>;

export const getSafeSynthesizerFormDefaults = (): SafeSynthesizerFormData => ({
  name: generateDefaultName(),
  description: '',
  spec: {
    data_source: '',
    config: {
      enable_synthesis: true,
      enable_replace_pii: true,
      training: {
        num_input_records_to_sample: 'auto',
        rope_scaling_factor: 'auto',
      },
      generation: {
        num_records: 1000,
        temperature: 0.9,
        top_p: 1,
        repetition_penalty: 1,
      },
      data: {},
      privacy: {
        dp_enabled: false,
      },
    },
  },
});
