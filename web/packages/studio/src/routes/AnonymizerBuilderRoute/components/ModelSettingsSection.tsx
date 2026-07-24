// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledSearchableSelect } from '@nemo/common/src/components/form/ControlledSearchableSelect';
import { ParamsDropdown } from '@nemo/common/src/components/ModelSelectV2/ParamsDropdown';
import { useModelsListProviders } from '@nemo/sdk/generated/platform/api';
import type { InferenceParams } from '@nemo/sdk/generated/platform/schema';
import { Divider, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import { modelsFromProviders } from '@studio/components/NewDataDesignerJobForm/utils';
import { DEFAULT_LARGE_PAGE_SIZE } from '@studio/constants/constants';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import {
  activeRolesForStrategy,
  GLINER_ROLE,
  ROLE_LABELS,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import type { AnonymizerFormData } from '@studio/routes/AnonymizerBuilderRoute/schema';
import { pickDefaultModelName } from '@studio/util/buildSuggestedModelOptions';
import { FC, useEffect, useMemo, useState } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

const isGliner = (name: string) => /gliner/i.test(name);

export const ModelSettingsSection: FC = () => {
  const { control, setValue, getValues } = useFormContext<AnonymizerFormData>();
  const workspace = useWorkspaceFromPath();
  const strategy = useWatch({ control, name: 'strategy' });
  const roleModelsValue = useWatch({ control, name: 'roleModels' });
  const [openParamsRole, setOpenParamsRole] = useState<string | null>(null);

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
    setValue(`roleModels.${role}.model`, selected?.served_model_name ?? '', {
      shouldValidate: true,
    });
    setValue(`roleModels.${role}.provider`, selected?.model_providers?.[0] ?? '', {
      shouldValidate: true,
    });
  };

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

  return (
    <Stack gap="density-2xl">
      {roles.map((role, index) => (
        <Stack key={role} gap="density-lg">
          {index > 0 && <Divider orientation="horizontal" width="small" />}
          <Text kind="label/bold/lg">{ROLE_LABELS[role] ?? role}</Text>
          <Flex gap="density-md" align="end">
            <div className="grow">
              <ControlledSearchableSelect
                aria-label={ROLE_LABELS[role] ?? role}
                options={items}
                isLoading={isLoading}
                triggerPlaceholder="Select a model"
                searchPlaceholder="Search models..."
                emptyMessage={isLoading ? 'Loading models...' : 'No models in this workspace.'}
                onChange={(value) => applyModel(role, value)}
                useControllerProps={{
                  name: `roleModels.${role}.modelId`,
                  control,
                }}
                formFieldProps={{ slotLabel: 'Model', required: true }}
              />
            </div>
            <ParamsDropdown
              open={openParamsRole === role}
              onOpenChange={(next) => setOpenParamsRole(next ? role : null)}
              inferenceParams={roleModelsValue?.[role]?.params as Partial<InferenceParams>}
              onInferenceParamsChange={(params) =>
                setValue(`roleModels.${role}.params`, params as Record<string, unknown>)
              }
            />
          </Flex>
        </Stack>
      ))}
    </Stack>
  );
};
