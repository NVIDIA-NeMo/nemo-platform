// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { RadioCard } from '@nemo/common/src/components/RadioCard';
import { RadioGroupRoot, Stack, Text } from '@nvidia/foundations-react-core';
import { FormSection } from '@studio/components/NewCustomizationForm/FormSection';
import type { CustomizationFormFields } from '@studio/util/forms/customization';
import { useFormContext } from 'react-hook-form';

const AUTOMODEL_FINETUNING_TYPES = [
  { value: 'lora', title: 'LoRA', description: 'Low-rank adapter — fewer parameters, less VRAM.' },
  {
    value: 'lora_merged',
    title: 'LoRA (Merged)',
    description: 'LoRA weights merged into base at the end.',
  },
  { value: 'all_weights', title: 'Full Weights', description: 'Train all model parameters.' },
] as const;

const UNSLOTH_FINETUNING_TYPES = [
  { value: 'lora', title: 'LoRA', description: 'Low-rank adapter — fewer parameters, less VRAM.' },
  { value: 'all_weights', title: 'Full Weights', description: 'Train all model parameters.' },
] as const;

const AUTOMODEL_TRAINING_TYPES = [
  {
    value: 'sft',
    title: 'SFT',
    description: 'Supervised fine-tuning on instruction/response pairs.',
  },
  {
    value: 'distillation',
    title: 'Distillation',
    description: 'Learn from a larger teacher model.',
  },
] as const;

export const TrainingMethodSection = () => {
  const { watch, setValue, control, formState } = useFormContext<CustomizationFormFields>();
  const backend = watch('backend');
  const disabled = formState.isSubmitting;

  const finetuningType =
    backend === 'automodel'
      ? watch('automodel.training.finetuning_type')
      : watch('unsloth.training.finetuning_type');

  const trainingType = backend === 'automodel' ? watch('automodel.training.training_type') : null;

  const finetuningOptions =
    backend === 'automodel' ? AUTOMODEL_FINETUNING_TYPES : UNSLOTH_FINETUNING_TYPES;

  const handleFinetuningChange = (value: string) => {
    if (backend === 'automodel') {
      setValue(
        'automodel.training.finetuning_type',
        value as CustomizationFormFields['automodel']['training']['finetuning_type'],
        { shouldValidate: true }
      );
    } else {
      setValue('unsloth.training.finetuning_type', value as 'lora' | 'all_weights', {
        shouldValidate: true,
      });
    }
  };

  return (
    <FormSection title="Training Method">
      <Stack gap="density-xl">
        <Stack gap="density-md">
          <Text kind="label/bold/md">Fine-tuning Type</Text>
          <RadioGroupRoot
            name="finetuningType"
            value={finetuningType ?? ''}
            onValueChange={handleFinetuningChange}
            className="w-full"
            disabled={disabled}
          >
            <Stack gap="density-sm">
              {finetuningOptions.map((opt) => (
                <RadioCard
                  key={opt.value}
                  value={opt.value}
                  label={<Text kind="body/bold/md">{opt.title}</Text>}
                  description={
                    <Text kind="body/regular/md" color="secondary">
                      {opt.description}
                    </Text>
                  }
                  labelSide="left"
                />
              ))}
            </Stack>
          </RadioGroupRoot>
        </Stack>

        {backend === 'automodel' && (
          <Stack gap="density-md">
            <Text kind="label/bold/md">Training Type</Text>
            <RadioGroupRoot
              name="trainingType"
              value={trainingType ?? 'sft'}
              onValueChange={(v) =>
                setValue('automodel.training.training_type', v as 'sft' | 'distillation', {
                  shouldValidate: true,
                })
              }
              className="w-full"
              disabled={disabled}
            >
              <Stack gap="density-sm">
                {AUTOMODEL_TRAINING_TYPES.map((opt) => (
                  <RadioCard
                    key={opt.value}
                    value={opt.value}
                    label={<Text kind="body/bold/md">{opt.title}</Text>}
                    description={
                      <Text kind="body/regular/md" color="secondary">
                        {opt.description}
                      </Text>
                    }
                    labelSide="left"
                  />
                ))}
              </Stack>
            </RadioGroupRoot>
            {trainingType === 'distillation' && (
              <ControlledTextInput
                useControllerProps={{ name: 'automodel.training.teacher_model', control }}
                label="Teacher Model"
                placeholder="workspace/model-name"
                required
                disabled={disabled}
              />
            )}
          </Stack>
        )}
      </Stack>
    </FormSection>
  );
};
