// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledSearchableSelect } from '@nemo/common/src/components/form/ControlledSearchableSelect';
import { useModelsListProviders } from '@nemo/sdk/generated/platform/api';
import { Divider, Stack, Text } from '@nvidia/foundations-react-core';
import { modelsFromProviders } from '@studio/components/NewDataDesignerJobForm/utils';
import { DEFAULT_LARGE_PAGE_SIZE } from '@studio/constants/constants';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import {
  activeRolesForStrategy,
  GLINER_ROLE,
  ROLE_LABELS,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import type { AnonymizerFormData } from '@studio/routes/AnonymizerBuilderRoute/schema';
import { FC, useEffect, useMemo } from 'react';
import { type Path, useFormContext, useWatch } from 'react-hook-form';

const isGliner = (name: string) => /gliner/i.test(name);

export const ModelSettingsSection: FC = () => {
  const { control, setValue, getValues } = useFormContext<AnonymizerFormData>();
  const workspace = useWorkspaceFromPath();
  const strategy = useWatch({ control, name: 'strategy' });

  const roles = useMemo(() => activeRolesForStrategy(strategy), [strategy]);

  const { data: providersPage, isLoading } = useModelsListProviders(
    workspace,
    { page_size: DEFAULT_LARGE_PAGE_SIZE },
    { query: {} }
  );

  const models = useMemo(
    () => modelsFromProviders(providersPage?.data ?? []),
    [providersPage?.data]
  );
  const items = useMemo(
    () => models.map((model) => ({ label: model.name, value: model.id })),
    [models]
  );

  const applyModel = (role: string, id: string) => {
    const selected = models.find((model) => model.id === id);
    setValue(
      `roleModels.${role}.model` as Path<AnonymizerFormData>,
      selected?.served_model_name ?? '',
      { shouldValidate: true }
    );
    setValue(
      `roleModels.${role}.provider` as Path<AnonymizerFormData>,
      selected?.model_providers?.[0] ?? '',
      { shouldValidate: true }
    );
  };

  // Seed sensible defaults once models load: GLiNER for the detector, an LLM for the rest.
  useEffect(() => {
    if (!models.length) return;
    const gliner = models.find((model) => isGliner(model.name)) ?? models[0];
    const llm = models.find((model) => !isGliner(model.name)) ?? models[0];
    for (const role of roles) {
      const current = getValues(`roleModels.${role}.modelId` as Path<AnonymizerFormData>);
      if (current) continue;
      const pick = role === GLINER_ROLE ? gliner : llm;
      setValue(`roleModels.${role}.modelId` as Path<AnonymizerFormData>, pick.id);
      applyModel(role, pick.id);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [models, roles, getValues, setValue]);

  return (
    <Stack gap="density-2xl">
      {roles.map((role, index) => (
        <Stack key={role} gap="density-lg">
          {index > 0 && <Divider orientation="horizontal" width="small" />}
          <Text kind="label/bold/lg">{ROLE_LABELS[role] ?? role}</Text>
          <ControlledSearchableSelect
            aria-label={ROLE_LABELS[role] ?? role}
            options={items}
            isLoading={isLoading}
            triggerPlaceholder="Select a model"
            searchPlaceholder="Search models..."
            emptyMessage={isLoading ? 'Loading models...' : 'No models in this workspace.'}
            onChange={(value) => applyModel(role, value)}
            useControllerProps={{
              name: `roleModels.${role}.modelId` as Path<AnonymizerFormData>,
              control,
            }}
            formFieldProps={{ slotLabel: 'Model', required: true }}
          />
        </Stack>
      ))}
    </Stack>
  );
};
