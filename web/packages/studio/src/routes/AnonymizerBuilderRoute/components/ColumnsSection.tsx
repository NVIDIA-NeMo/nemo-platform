// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledTextArea } from '@nemo/common/src/components/form/ControlledTextArea';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { Stack, Text } from '@nvidia/foundations-react-core';
import type { AnonymizerFormData } from '@studio/routes/AnonymizerBuilderRoute/schema';
import { FC } from 'react';
import { useFormContext } from 'react-hook-form';

export const ColumnsSection: FC = () => {
  const { control } = useFormContext<AnonymizerFormData>();

  return (
    <Stack gap="density-lg">
      <Text kind="label/bold/lg">Columns</Text>
      <ControlledTextInput
        useControllerProps={{ name: 'textColumn', control }}
        placeholder="e.g. biography"
        formFieldProps={{
          slotLabel: 'Text Column',
          slotInfo: 'The column containing the text to anonymize.',
        }}
      />
      <ControlledTextArea
        useControllerProps={{ name: 'dataSummary', control }}
        formFieldProps={{
          slotLabel: 'Data Summary',
          slotInfo: 'Optional short description of the data. Helps the LLM produce better results.',
        }}
      />
    </Stack>
  );
};
