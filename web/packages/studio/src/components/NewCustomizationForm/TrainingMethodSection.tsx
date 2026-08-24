// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledTextInput } from '@nemo/common/src/components/form/ControlledTextInput';
import { RadioCard } from '@nemo/common/src/components/RadioCard';
import {
  AutomodelTrainingSpecFinetuningType,
  AutomodelTrainingSpecTrainingType,
  UnslothTrainingSpecFinetuningType,
} from '@nemo/sdk/generated/customizer/schema';
import { RadioGroupRoot, Stack, Text } from '@nvidia/foundations-react-core';
import { FormSection } from '@studio/components/NewCustomizationForm/FormSection';
import {
  RL_DPO_TRAINING_DEFAULTS,
  RL_GRPO_TRAINING_DEFAULTS,
  type CustomizationFormFields,
} from '@studio/util/forms/customization';
import { useFormContext } from 'react-hook-form';

const AUTOMODEL_FINETUNING_TYPES = [
  {
    value: AutomodelTrainingSpecFinetuningType.lora,
    title: 'LoRA',
    description: 'Low-rank adapter — fewer parameters, less VRAM.',
  },
  {
    value: AutomodelTrainingSpecFinetuningType.lora_merged,
    title: 'LoRA (Merged)',
    description: 'LoRA weights merged into base at the end.',
  },
  {
    value: AutomodelTrainingSpecFinetuningType.all_weights,
    title: 'Full Weights',
    description: 'Train all model parameters.',
  },
] as const;

const UNSLOTH_FINETUNING_TYPES = [
  {
    value: UnslothTrainingSpecFinetuningType.lora,
    title: 'LoRA',
    description: 'Low-rank adapter — fewer parameters, less VRAM.',
  },
  {
    value: UnslothTrainingSpecFinetuningType.all_weights,
    title: 'Full Weights',
    description: 'Train all model parameters.',
  },
] as const;

/**
 * Bound to `grpo.trainingType` rather than `rl.training.type`: the form holds one
 * `rl.training` object, and flipping the union discriminator in place would leave it
 * carrying the other arm's fields. `formToRlCreate` sets `type` from this on submit.
 */
const RL_TRAINING_TYPES = [
  {
    value: 'dpo',
    title: 'DPO',
    description: 'Direct Preference Optimization — full-weight fine-tuning on preference pairs.',
  },
  {
    value: 'grpo',
    title: 'GRPO',
    description: 'Group Relative Policy Optimization — RL fine-tuning with a reward environment.',
  },
] as const;

const AUTOMODEL_TRAINING_TYPES = [
  {
    value: AutomodelTrainingSpecTrainingType.sft,
    title: 'SFT',
    description: 'Supervised fine-tuning on instruction/response pairs.',
  },
  {
    value: AutomodelTrainingSpecTrainingType.distillation,
    title: 'Distillation',
    description: 'Learn from a larger teacher model.',
  },
] as const;

export const TrainingMethodSection = () => {
  const { watch, setValue, getValues, control, formState } =
    useFormContext<CustomizationFormFields>();
  const backend = watch('backend');
  const disabled = formState.isSubmitting;

  if (backend === 'rl') {
    const rlTrainingType = watch('grpo.trainingType');
    return (
      <FormSection title="Training Method">
        <RadioGroupRoot
          name="rlTrainingType"
          value={rlTrainingType ?? 'dpo'}
          onValueChange={(v) => {
            const next = v as 'dpo' | 'grpo';
            setValue('grpo.trainingType', next, { shouldValidate: true });
            // rl.training is shared by both methods, and the two default sets differ
            // only in max_steps, val_at_end and ref_policy_kl_penalty. Reset to the
            // incoming method's defaults so DPO cannot inherit GRPO's step budget and
            // skipped end validation, but carry over the fields that mean the same
            // thing under either method so a switch does not discard the user's work.
            const current = getValues('rl.training');
            setValue(
              'rl.training',
              {
                ...(next === 'grpo' ? RL_GRPO_TRAINING_DEFAULTS : RL_DPO_TRAINING_DEFAULTS),
                parallelism: current.parallelism,
                learning_rate: current.learning_rate,
                batch_size: current.batch_size,
                max_seq_length: current.max_seq_length,
              },
              { shouldValidate: true }
            );
          }}
          className="w-full"
          disabled={disabled}
        >
          <div className="grid grid-cols-2 gap-4">
            {RL_TRAINING_TYPES.map((opt) => (
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
          </div>
        </RadioGroupRoot>
      </FormSection>
    );
  }

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
      setValue('unsloth.training.finetuning_type', value as UnslothTrainingSpecFinetuningType, {
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
            <div className="grid grid-cols-2 gap-4">
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
            </div>
          </RadioGroupRoot>
        </Stack>

        {backend === 'automodel' && (
          <Stack gap="density-md">
            <Text kind="label/bold/md">Training Type</Text>
            <RadioGroupRoot
              name="trainingType"
              value={trainingType ?? 'sft'}
              onValueChange={(v) =>
                setValue(
                  'automodel.training.training_type',
                  v as AutomodelTrainingSpecTrainingType,
                  {
                    shouldValidate: true,
                  }
                )
              }
              className="w-full"
              disabled={disabled}
            >
              <div className="grid grid-cols-2 gap-4">
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
              </div>
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
