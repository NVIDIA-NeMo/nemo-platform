// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledSliderWithTextInput } from '@nemo/common/src/components/form/ControlledSliderWithTextInput';
import { ControlledSwitch } from '@nemo/common/src/components/form/ControlledSwitch';
import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { ControlledJsonInput } from '@studio/components/NewCustomizationForm/ControlledJsonInput';
import { FormSection } from '@studio/components/NewCustomizationForm/FormSection';
import type { CustomizationFormFields } from '@studio/util/forms/customization';
import { useFormContext } from 'react-hook-form';

const AutomodelParallelism = ({ disabled }: { disabled: boolean }) => {
  const { control } = useFormContext<CustomizationFormFields>();
  return (
    <Stack gap="density-lg">
      <ControlledSliderWithTextInput
        useControllerProps={{ name: 'automodel.parallelism.num_nodes', control }}
        formFieldProps={{ slotLabel: 'Nodes' }}
        defaultValue={1}
        min={1}
        max={16}
        step={1}
        disabled={disabled}
      />
      <ControlledSliderWithTextInput
        useControllerProps={{ name: 'automodel.parallelism.num_gpus_per_node', control }}
        formFieldProps={{ slotLabel: 'GPUs per Node' }}
        defaultValue={1}
        min={1}
        max={8}
        step={1}
        disabled={disabled}
      />
      <AccordionRoot multiple>
        <AccordionItem value="advanced-parallelism" className="border-b-0">
          <AccordionTrigger>
            <Text kind="label/bold/md">Advanced Parallelism</Text>
          </AccordionTrigger>
          <AccordionContent>
            <Stack gap="density-md" className="pt-density-md">
              <ControlledSliderWithTextInput
                useControllerProps={{ name: 'automodel.parallelism.tensor_parallel_size', control }}
                formFieldProps={{ slotLabel: 'Tensor Parallel Size' }}
                defaultValue={1}
                min={1}
                max={8}
                step={1}
                disabled={disabled}
              />
              <ControlledSliderWithTextInput
                useControllerProps={{
                  name: 'automodel.parallelism.pipeline_parallel_size',
                  control,
                }}
                formFieldProps={{ slotLabel: 'Pipeline Parallel Size' }}
                defaultValue={1}
                min={1}
                max={8}
                step={1}
                disabled={disabled}
              />
              <ControlledSliderWithTextInput
                useControllerProps={{
                  name: 'automodel.parallelism.context_parallel_size',
                  control,
                }}
                formFieldProps={{ slotLabel: 'Context Parallel Size' }}
                defaultValue={1}
                min={1}
                max={8}
                step={1}
                disabled={disabled}
              />
              <ControlledSwitch
                useControllerProps={{ name: 'automodel.parallelism.sequence_parallel', control }}
                formFieldProps={{ slotLabel: 'Sequence Parallel', labelPosition: 'left' }}
                disabled={disabled}
              />
            </Stack>
          </AccordionContent>
        </AccordionItem>
      </AccordionRoot>
    </Stack>
  );
};

const UnslothHardware = ({ disabled }: { disabled: boolean }) => {
  const { control } = useFormContext<CustomizationFormFields>();
  return (
    <Stack gap="density-lg">
      <ControlledTextInput
        useControllerProps={{ name: 'unsloth.hardware.gpus', control }}
        label="GPU Indices"
        placeholder="0  or  0,1"
        disabled={disabled}
      />
      <ControlledJsonInput
        useControllerProps={{ name: 'unsloth.deployment_config', control }}
        formFieldProps={{ slotLabel: 'Deployment Config (name or JSON)' }}
        placeholder='"my-config"  or  { "gpu": 1 }'
        disabled={disabled}
      />
    </Stack>
  );
};

export const ComputeResourcesSection = () => {
  const { watch, formState } = useFormContext<CustomizationFormFields>();
  const backend = watch('backend');
  const disabled = formState.isSubmitting;

  return (
    <FormSection title="Compute Resources">
      {backend === 'automodel' ? (
        <AutomodelParallelism disabled={disabled} />
      ) : (
        <UnslothHardware disabled={disabled} />
      )}
    </FormSection>
  );
};
