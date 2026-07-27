// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  activeRolesForStrategy,
  GLINER_ROLE,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import type { AnonymizerFormData } from '@studio/routes/AnonymizerBuilderRoute/schema';
import { useAnonymizerModels } from '@studio/routes/AnonymizerBuilderRoute/useAnonymizerModels';
import { pickDefaultModelName } from '@studio/util/buildSuggestedModelOptions';
import { useEffect, useMemo } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

const isGliner = (name: string) => /gliner/i.test(name);

/**
 * Seeds a model for every role the strategy needs. Lives at the route rather than in
 * ModelSettingsSection so the defaults still land when that tab is never opened.
 */
export const useDefaultRoleModels = (): { isLoading: boolean } => {
  const { control, setValue, getValues } = useFormContext<AnonymizerFormData>();
  const strategy = useWatch({ control, name: 'strategy' });
  const { models, isLoading, applyModel } = useAnonymizerModels();

  const roles = useMemo(() => activeRolesForStrategy(strategy), [strategy]);

  useEffect(() => {
    if (!models.length) return;
    const suggestedName = pickDefaultModelName(
      models.map((model) => ({ name: model.served_model_name ?? model.name }))
    );
    const llm =
      models.find((model) => (model.served_model_name ?? model.name) === suggestedName) ??
      models.find((model) => !isGliner(model.name)) ??
      models[0];
    const gliner = models.find((model) => isGliner(model.name)) ?? llm;
    for (const role of roles) {
      const current = getValues(`roleModels.${role}.modelId`);
      if (current) continue;
      const pick = role === GLINER_ROLE ? gliner : llm;
      setValue(`roleModels.${role}.modelId`, pick.id);
      applyModel(role, pick.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [models, roles, getValues, setValue]);

  return { isLoading };
};
