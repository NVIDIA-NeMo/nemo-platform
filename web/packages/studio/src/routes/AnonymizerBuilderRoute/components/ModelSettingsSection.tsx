// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { useModelsListProviders } from '@nemo/sdk/generated/platform/api';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { modelsFromProviders } from '@studio/components/NewDataDesignerJobForm/utils';
import { DEFAULT_LARGE_PAGE_SIZE } from '@studio/constants/constants';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import type { AnonymizerFormData } from '@studio/routes/AnonymizerBuilderRoute/schema';
import { FC, useMemo } from 'react';
import { useFormContext } from 'react-hook-form';

export const ModelSettingsSection: FC = () => {
  const { control, setValue } = useFormContext<AnonymizerFormData>();
  const workspace = useWorkspaceFromPath();

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

  const handleChange = (id: string) => {
    const selected = models.find((model) => model.id === id);
    setValue('model', selected?.served_model_name ?? '', { shouldValidate: true });
    setValue('provider', selected?.model_providers?.[0] ?? '', { shouldValidate: true });
  };

  return (
    <Stack gap="density-lg">
      <Text kind="label/bold/lg">Model Settings</Text>
      <Text kind="body/regular/md">
        Select the inference provider model the Anonymizer uses for entity detection and generation.
      </Text>
      <ControlledSelect
        aria-label="Model"
        items={items}
        loading={isLoading}
        placeholder="Select a model"
        onChange={(value) => handleChange(value as string)}
        useControllerProps={{ name: 'modelId', control }}
        formFieldProps={{ slotLabel: 'Model', required: true }}
      />
    </Stack>
  );
};
