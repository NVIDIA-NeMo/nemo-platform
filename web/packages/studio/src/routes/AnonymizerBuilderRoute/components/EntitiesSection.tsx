// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledCheckbox } from '@nemo/common/src/components/form/ControlledCheckbox';
import { ControlledSegmentedControl } from '@nemo/common/src/components/form/ControlledSegmentedControl';
import { Stack, Text } from '@nvidia/foundations-react-core';
import {
  ENTITY_MODE_AUTO,
  ENTITY_MODE_OPTIONS,
} from '@studio/routes/AnonymizerBuilderRoute/constants';
import type { AnonymizerFormData } from '@studio/routes/AnonymizerBuilderRoute/schema';
import { FC } from 'react';
import { useFormContext, useWatch } from 'react-hook-form';

export const EntitiesSection: FC = () => {
  const { control } = useFormContext<AnonymizerFormData>();
  const entityMode = useWatch({ control, name: 'entityMode' });

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
      <ControlledCheckbox
        useControllerProps={{ name: 'includeDefaultEntities', control }}
        formFieldProps={{ slotLabel: 'Include all default entities' }}
      />
    </Stack>
  );
};
