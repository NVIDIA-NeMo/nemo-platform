// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledCheckbox } from '@nemo/common/src/components/form/ControlledCheckbox';
import { ControlledCombobox } from '@nemo/common/src/components/form/ControlledCombobox';
import { ControlledSegmentedControl } from '@nemo/common/src/components/form/ControlledSegmentedControl';
import { useAnonymizerListEntityLabels } from '@nemo/sdk/generated/anonymizer/api';
import { Stack, Text } from '@nvidia/foundations-react-core';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import {
  ENTITY_MODE_AUTO,
  ENTITY_MODE_CUSTOM,
  ENTITY_MODE_OPTIONS,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import type { AnonymizerFormData } from '@studio/routes/AnonymizerBuilderRoute/schema';
import { FC } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

export const EntitiesSection: FC = () => {
  const { control } = useFormContext<AnonymizerFormData>();
  const workspace = useWorkspaceFromPath();
  const entityMode = useWatch({ control, name: 'entityMode' });
  const includeDefaults = useWatch({ control, name: 'includeDefaultEntities' });

  const isCustom = entityMode === ENTITY_MODE_CUSTOM;
  const showLabelPicker = isCustom && !includeDefaults;

  const { data, isLoading } = useAnonymizerListEntityLabels(workspace, { query: {} });
  const labels = data?.data ?? [];

  return (
    <Stack gap="density-lg">
      <Text kind="label/bold/lg">Entities</Text>
      <ControlledSegmentedControl
        className="w-full"
        size="tiny"
        items={ENTITY_MODE_OPTIONS}
        useControllerProps={{ name: 'entityMode', control }}
      />
      <Text kind="body/regular/md">
        {entityMode === ENTITY_MODE_AUTO
          ? 'Auto-detect lets the augmenter create additional labels beyond the defaults.'
          : 'Custom mode only outputs entities you define. Use Auto-detect to allow additional labels.'}
      </Text>
      {isCustom && (
        <ControlledCheckbox
          useControllerProps={{ name: 'includeDefaultEntities', control }}
          formFieldProps={{ slotLabel: 'Include all default entities' }}
        />
      )}
      {showLabelPicker && (
        <ControlledCombobox
          kind="multiple"
          loading={isLoading}
          items={labels}
          useControllerProps={{ name: 'entityLabels', control }}
          formFieldProps={{
            slotLabel: 'Entity Labels',
            slotInfo: 'Only these entity types will be detected and replaced.',
          }}
        />
      )}
    </Stack>
  );
};
