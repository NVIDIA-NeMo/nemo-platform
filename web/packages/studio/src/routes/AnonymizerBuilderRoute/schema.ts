// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import type {
  AnonymizerConfigInput,
  ModelConfig,
  RunJobRequest,
  SelectedModelsOverrides,
} from '@nemo/sdk/generated/anonymizer/schema';
import {
  activeRolesForStrategy,
  DETECTION_ROLES,
  DEFAULT_PREVIEW_ROWS,
  ENTITY_MODE_CUSTOM,
  REPLACE_ROLE,
  REWRITE_ROLES,
  REWRITE_STRATEGY,
  SOURCE_TYPE_DATASET,
  STRATEGY_SUBSTITUTE,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import { z } from 'zod';

const roleModelSchema = z.object({
  modelId: z.string(),
  model: z.string(),
  provider: z.string(),
  params: z.record(z.string(), z.unknown()).optional(),
});

export const anonymizerFormSchema = z
  .object({
    name: z.string().optional(),
    sourceType: z.enum(['url', 'dataset']),
    source: z.string().min(1, 'A data source is required'),
    strategy: z.enum(['substitute', 'redact', 'annotate', 'hash', 'rewrite']),
    previewRows: z.number().int().min(1),
    textColumn: z.string().optional(),
    dataSummary: z.string().optional(),
    entityMode: z.enum([ENTITY_MODE_CUSTOM, 'auto']),
    includeDefaultEntities: z.boolean(),
    roleModels: z.record(z.string(), roleModelSchema),
  })
  .superRefine((data, ctx) => {
    for (const role of activeRolesForStrategy(data.strategy)) {
      const roleModel = data.roleModels[role];
      if (!roleModel?.model || !roleModel?.provider) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['roleModels', role, 'modelId'],
          message: 'Select a model',
        });
      }
    }
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
  roleModels: {},
});

const trimToUndefined = (value: string | undefined): string | undefined => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
};

/**
 * Build the create-job request. The strategy is applied via `config.rewrite`
 * for Rewrite and `config.replace` for the other four. `replace` is a
 * `kind`-discriminated union server-side, so the tag must be sent even though
 * it isn't a modelled field on the SDK types.
 *
 * Each active role's model is deduplicated into a `model_configs` pool (one
 * entry per unique model+provider) and `selected_models` maps every role of
 * the strategy's workflow(s) to the matching alias.
 */
export const buildAnonymizerJobRequest = (form: AnonymizerFormData): RunJobRequest => {
  const config: AnonymizerConfigInput =
    form.strategy === REWRITE_STRATEGY
      ? { rewrite: {} }
      : { replace: { kind: form.strategy } as AnonymizerConfigInput['replace'] };

  const aliasByModel = new Map<string, string>();
  const modelConfigs: ModelConfig[] = [];
  const aliasForRole: Record<string, string> = {};

  for (const role of activeRolesForStrategy(form.strategy)) {
    const roleModel = form.roleModels[role];
    const model = roleModel?.model.trim() ?? '';
    const provider = roleModel?.provider.trim() ?? '';
    const params = roleModel?.params;
    const hasParams = params != null && Object.keys(params).length > 0;
    const key = `${provider}::${model}::${hasParams ? JSON.stringify(params) : ''}`;
    let alias = aliasByModel.get(key);
    if (!alias) {
      alias = `model-${aliasByModel.size + 1}`;
      aliasByModel.set(key, alias);
      modelConfigs.push({
        alias,
        model,
        provider,
        ...(hasParams
          ? { inference_parameters: params as ModelConfig['inference_parameters'] }
          : {}),
      });
    }
    aliasForRole[role] = alias;
  }

  const toRoleMap = (roles: string[]) =>
    Object.fromEntries(roles.map((role) => [role, aliasForRole[role]]));

  const selectedModels: SelectedModelsOverrides = { detection: toRoleMap(DETECTION_ROLES) };
  if (form.strategy === REWRITE_STRATEGY) {
    selectedModels.rewrite = toRoleMap(REWRITE_ROLES);
  } else if (form.strategy === STRATEGY_SUBSTITUTE) {
    selectedModels.replace = { [REPLACE_ROLE]: aliasForRole[REPLACE_ROLE] };
  }

  return {
    name: trimToUndefined(form.name),
    spec: {
      config,
      data: {
        source: form.source.trim(),
        text_column: trimToUndefined(form.textColumn),
        data_summary: trimToUndefined(form.dataSummary),
      },
      model_configs: modelConfigs,
      selected_models: selectedModels,
    },
  };
};
