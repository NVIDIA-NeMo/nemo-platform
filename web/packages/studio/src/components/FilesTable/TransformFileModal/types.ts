// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getRequiredKeys,
  TARGET_FORMATS,
  TargetFormat,
} from '@studio/components/FilesTable/TransformFileModal/targetFormats';
import { z } from 'zod';

export const mappingSchema = z.object({
  /** Empty key is allowed for the trailing draft row in MappingFields. */
  key: z.string(),
  value: z.string().optional(),
});

export const transformFileSchema = z
  .object({
    filepath: z.string().nonempty('Filepath is required'),
    outputFilepath: z.string().nonempty('Output file is required'),
    targetFormat: z.enum(TARGET_FORMATS),
    model: z.string().optional(),
    mappings: z.array(mappingSchema),
  })
  .refine((data) => data.outputFilepath.trim() !== data.filepath.trim(), {
    path: ['outputFilepath'],
    message: 'The transform writes a new file. Choose a name other than the source file.',
  })
  .superRefine((data, ctx) => {
    for (const requiredKey of getRequiredKeys(data.targetFormat)) {
      const index = data.mappings.findIndex((mapping) => mapping.key.trim() === requiredKey);
      if (index >= 0 && data.mappings[index].value?.trim()) continue;
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `"${requiredKey}" is required by the task format. Map it to a source column or a literal value.`,
        path: ['mappings', index >= 0 ? index : 0, 'value'],
      });
    }
  })
  .superRefine((data, ctx) => {
    const keys = new Set<string>();
    for (let i = 0; i < data.mappings.length; i++) {
      const k = data.mappings[i].key.trim();
      if (!k) continue;
      if (keys.has(k)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: 'Mapping keys must be unique.',
          path: ['mappings', i, 'key'],
        });
        break;
      }
      keys.add(k);
    }
  })
  .refine(
    (data) => {
      if (!data.model) {
        return true;
      }
      const hasUserMsg = data.mappings.some(
        (mapping) =>
          mapping.key === 'prompt' || mapping.key === 'instruction' || mapping.key === 'question'
      );
      if (!hasUserMsg) {
        return false;
      }
      return true;
    },
    {
      path: ['model'],
      message:
        'Missing user message for model inference. Please add a mapping with a key of "prompt", "instruction", or "question".',
    }
  );

export type TransformFileFormFields = {
  filepath: string;
  outputFilepath: string;
  targetFormat: TargetFormat;
  model?: string;
  mappings: z.infer<typeof mappingSchema>[];
};
