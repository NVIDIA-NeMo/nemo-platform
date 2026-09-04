// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledSwitch } from '@nemo/common/src/components/form/ControlledSwitch';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { Flex } from '@nvidia/foundations-react-core';
import { WizardFormValues } from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/schema';
import { Control, FieldErrors } from 'react-hook-form';

export const GPULoraFields = ({
  control,
  errors,
}: {
  control: Control<WizardFormValues>;
  errors: FieldErrors<WizardFormValues>;
}) => {
  return (
    <Flex gap="4" align="start" className="w-full">
      <Flex className="flex-1">
        <ControlledTextInput
          useControllerProps={{ control, name: 'gpu' }}
          name="gpu"
          label="GPUs"
          type="number"
          formFieldProps={{
            slotInfo: 'GPU count for this NIM (TP×PP for multi-LLM NIM; see docs).',
            slotError: errors.gpu?.message,
          }}
        />
      </Flex>
      <Flex className="flex-1 shrink-0 ">
        <ControlledSwitch
          useControllerProps={{ control, name: 'loraEnabled' }}
          attributes={{ Flex: { justify: 'start' } }}
          formFieldProps={{
            slotLabel: 'LoRA Enabled',
            slotInfo: 'Enable when serving LoRA adapters on this base image.',
          }}
        />
      </Flex>
    </Flex>
  );
};
