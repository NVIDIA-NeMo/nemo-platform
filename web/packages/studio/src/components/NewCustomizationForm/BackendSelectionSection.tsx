// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RadioCard } from '@nemo/common/src/components/RadioCard';
import { RadioGroupRoot, Stack, Text } from '@nvidia/foundations-react-core';
import { FormSection } from '@studio/components/NewCustomizationForm/FormSection';
import type { CustomizationFormFields } from '@studio/util/forms/customization';
import { useFormContext } from 'react-hook-form';

const BACKENDS = [
  {
    value: 'automodel' as const,
    title: 'Automodel',
    description:
      'Multi-GPU distributed training. Supports SFT and knowledge distillation with LoRA or full-weight fine-tuning.',
  },
  {
    value: 'unsloth' as const,
    title: 'Unsloth',
    description:
      'Single-GPU, memory-efficient training via 4-bit quantization. Ideal for smaller hardware with fast iteration.',
  },
];

export const BackendSelectionSection = () => {
  const { watch, setValue, formState } = useFormContext<CustomizationFormFields>();
  const backend = watch('backend');
  const disabled = formState.isSubmitting;

  return (
    <FormSection title="Training Backend">
      <RadioGroupRoot
        name="backend"
        value={backend}
        onValueChange={(v) =>
          setValue('backend', v as CustomizationFormFields['backend'], { shouldValidate: false })
        }
        className="w-full"
        disabled={disabled}
      >
        <Stack gap="density-md">
          {BACKENDS.map((b) => (
            <RadioCard
              key={b.value}
              value={b.value}
              label={<Text kind="body/bold/lg">{b.title}</Text>}
              description={
                <Text kind="body/regular/md" color="secondary">
                  {b.description}
                </Text>
              }
              labelSide="left"
            />
          ))}
        </Stack>
      </RadioGroupRoot>
    </FormSection>
  );
};
