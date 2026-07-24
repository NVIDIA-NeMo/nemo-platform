// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import type { AnonymizerConfigInput, RunJobRequest } from '@nemo/sdk/generated/anonymizer/schema';
import {
  DEFAULT_PREVIEW_ROWS,
  ENTITY_MODE_CUSTOM,
  REWRITE_STRATEGY,
  SOURCE_TYPE_DATASET,
  STRATEGY_SUBSTITUTE,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import { z } from 'zod';

export const anonymizerFormSchema = z.object({
  name: z.string().optional(),
  sourceType: z.enum(['url', 'dataset']),
  source: z.string().min(1, 'A data source is required'),
  strategy: z.enum(['substitute', 'redact', 'annotate', 'hash', 'rewrite']),
  previewRows: z.number().int().min(1),
  textColumn: z.string().optional(),
  dataSummary: z.string().optional(),
  entityMode: z.enum([ENTITY_MODE_CUSTOM, 'auto']),
  includeDefaultEntities: z.boolean(),
});

export type AnonymizerFormData = z.infer<typeof anonymizerFormSchema>;

export const getAnonymizerFormDefaults = (): AnonymizerFormData => ({
  name: generateDefaultName(),
  sourceType: SOURCE_TYPE_DATASET,
  source: '',
  strategy: STRATEGY_SUBSTITUTE,
  previewRows: DEFAULT_PREVIEW_ROWS,
  textColumn: '',
  dataSummary: '',
  entityMode: ENTITY_MODE_CUSTOM,
  includeDefaultEntities: true,
});

const trimToUndefined = (value: string | undefined): string | undefined => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
};

/**
 * Build the create-job request. The strategy is applied via `config.rewrite`
 * for Rewrite and `config.replace` for the other four. `replace` is a
 * `kind`-discriminated union server-side, so the tag must be sent even though
 * it isn't a modelled field on the SDK types. Strategy-specific parameters
 * (templates, hash length, risk tolerance, …) are added in a follow-up.
 */
export const buildAnonymizerJobRequest = (form: AnonymizerFormData): RunJobRequest => {
  const config: AnonymizerConfigInput =
    form.strategy === REWRITE_STRATEGY
      ? { rewrite: {} }
      : { replace: { kind: form.strategy } as AnonymizerConfigInput['replace'] };

  return {
    name: trimToUndefined(form.name),
    spec: {
      config,
      data: {
        source: form.source.trim(),
        text_column: trimToUndefined(form.textColumn),
        data_summary: trimToUndefined(form.dataSummary),
      },
    },
  };
};
