// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { ControlledSliderWithTextInput } from '@nemo/common/src/components/form/ControlledSliderWithTextInput';
import { ControlledSwitch } from '@nemo/common/src/components/form/ControlledSwitch';
import {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { OPTIMIZER_TYPE_ITEMS } from '@studio/components/NewCustomizationForm/constants';
import { ControlledJsonInput } from '@studio/components/NewCustomizationForm/ControlledJsonInput';
import { FormSection } from '@studio/components/NewCustomizationForm/FormSection';
import type { CustomizationFormFields } from '@studio/util/forms/customization';
import { useFormContext } from 'react-hook-form';

export const GeneralParametersSection = () => {
  const { control, watch, formState } = useFormContext<CustomizationFormFields>();
  const backend = watch('backend');
  const disabled = formState.isSubmitting;

  if (backend === 'rl') {
    return (
      <FormSection title="Training Parameters">
        <Stack gap="density-lg">
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'rl.training.epochs', control }}
            formFieldProps={{ slotLabel: 'Epochs' }}
            defaultValue={1}
            min={1}
            max={100}
            step={1}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'rl.training.learning_rate', control }}
            formFieldProps={{ slotLabel: 'Learning Rate' }}
            defaultValue={1e-4}
            min={1e-6}
            max={1e-3}
            step={1e-6}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'rl.training.batch_size', control }}
            formFieldProps={{ slotLabel: 'Global Batch Size' }}
            defaultValue={32}
            min={1}
            max={256}
            step={1}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'rl.training.max_seq_length', control }}
            formFieldProps={{ slotLabel: 'Max Sequence Length' }}
            defaultValue={2048}
            min={128}
            max={131072}
            step={128}
            disabled={disabled}
          />
          <AccordionRoot multiple>
            <AccordionItem value="advanced" className="border-b-0">
              <AccordionTrigger>
                <Text kind="label/bold/md">Advanced</Text>
              </AccordionTrigger>
              <AccordionContent>
                <Stack gap="density-md" className="pt-density-md">
                  {/*
                    No Max Steps control here on purpose. DPO run length is driven by
                    Epochs, matching the backend default (`max_steps: None`), so
                    `RL_DPO_TRAINING_DEFAULTS` leaves it unset. A slider must declare a
                    reset target, and any number it resets to would silently switch the
                    run to a step budget — max_steps overrides epochs. GRPO exposes it
                    because GRPO genuinely defaults to a step budget.
                  */}
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'rl.training.micro_batch_size', control }}
                    formFieldProps={{ slotLabel: 'Micro Batch Size' }}
                    defaultValue={1}
                    min={1}
                    max={64}
                    step={1}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'rl.training.warmup_steps', control }}
                    formFieldProps={{ slotLabel: 'Warmup Steps' }}
                    defaultValue={0}
                    min={0}
                    max={1000}
                    step={1}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'rl.training.weight_decay', control }}
                    formFieldProps={{ slotLabel: 'Weight Decay' }}
                    defaultValue={0.01}
                    min={0}
                    max={1}
                    step={0.01}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'rl.training.seed', control }}
                    formFieldProps={{
                      slotLabel: 'Seed',
                      slotInfo: 'Random seed for reproducibility.',
                    }}
                    defaultValue={42}
                    min={0}
                    max={999999}
                    step={1}
                    disabled={disabled}
                  />
                  <ControlledSwitch
                    useControllerProps={{ name: 'rl.training.activation_checkpointing', control }}
                    formFieldProps={{
                      slotLabel: 'Activation Checkpointing',
                      labelPosition: 'left',
                      slotInfo:
                        'Recompute activations during the backward pass to reduce memory at the cost of compute.',
                    }}
                    disabled={disabled}
                  />
                  <ControlledSelect
                    useControllerProps={{ name: 'rl.training.optimizer_type', control }}
                    formFieldProps={{ slotLabel: 'Optimizer Type' }}
                    items={OPTIMIZER_TYPE_ITEMS}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'rl.training.min_learning_rate', control }}
                    formFieldProps={{
                      slotLabel: 'Min Learning Rate',
                      slotInfo: 'Minimum LR for cosine decay.',
                    }}
                    defaultValue={0}
                    min={0}
                    max={1e-3}
                    step={1e-6}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'rl.training.adam_beta1', control }}
                    formFieldProps={{ slotLabel: 'Adam β₁' }}
                    defaultValue={0.9}
                    min={0}
                    max={0.999}
                    step={0.001}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'rl.training.adam_beta2', control }}
                    formFieldProps={{ slotLabel: 'Adam β₂' }}
                    defaultValue={0.999}
                    min={0}
                    max={0.9999}
                    step={0.0001}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'rl.training.adam_eps', control }}
                    formFieldProps={{
                      slotLabel: 'Adam ε',
                      slotInfo: 'Numerical stability term.',
                    }}
                    defaultValue={1e-8}
                    min={1e-10}
                    max={1e-6}
                    step={1e-10}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'rl.training.val_check_interval', control }}
                    formFieldProps={{
                      slotLabel: 'Val Check Interval',
                      slotInfo:
                        'Validation frequency. Values ≤ 1.0 are a fraction of an epoch; values > 1.0 are a step count.',
                    }}
                    defaultValue={1.0}
                    min={0.01}
                    max={10}
                    step={0.01}
                    disabled={disabled}
                  />
                  <ControlledSwitch
                    useControllerProps={{ name: 'rl.training.val_at_end', control }}
                    formFieldProps={{
                      slotLabel: 'Validate at End',
                      labelPosition: 'left',
                      slotInfo: 'Run a final validation pass after the last training step.',
                    }}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'rl.training.keep_top_k', control }}
                    formFieldProps={{
                      slotLabel: 'Keep Top-K Checkpoints',
                      slotInfo: 'Number of best checkpoints to retain, ranked by validation loss.',
                    }}
                    defaultValue={1}
                    min={1}
                    max={10}
                    step={1}
                    disabled={disabled}
                  />
                </Stack>
              </AccordionContent>
            </AccordionItem>
          </AccordionRoot>
        </Stack>
      </FormSection>
    );
  }

  if (backend === 'automodel') {
    return (
      <FormSection title="Training Parameters">
        <Stack gap="density-lg">
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'automodel.schedule.epochs', control }}
            formFieldProps={{ slotLabel: 'Epochs' }}
            defaultValue={1}
            min={1}
            max={100}
            step={1}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'automodel.optimizer.learning_rate', control }}
            formFieldProps={{ slotLabel: 'Learning Rate' }}
            defaultValue={5e-6}
            min={1e-6}
            max={1e-3}
            step={1e-6}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'automodel.batch.global_batch_size', control }}
            formFieldProps={{ slotLabel: 'Global Batch Size' }}
            defaultValue={8}
            min={1}
            max={256}
            step={1}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'automodel.training.max_seq_length', control }}
            formFieldProps={{ slotLabel: 'Max Sequence Length' }}
            defaultValue={2048}
            min={128}
            max={131072}
            step={128}
            disabled={disabled}
          />
          <ControlledSwitch
            useControllerProps={{ name: 'automodel.batch.sequence_packing', control }}
            formFieldProps={{ slotLabel: 'Sequence Packing', labelPosition: 'left' }}
            disabled={disabled}
          />
          <AccordionRoot multiple>
            <AccordionItem value="advanced" className="border-b-0">
              <AccordionTrigger>
                <Text kind="label/bold/md">Advanced</Text>
              </AccordionTrigger>
              <AccordionContent>
                <Stack gap="density-md" className="pt-density-md">
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'automodel.batch.micro_batch_size', control }}
                    formFieldProps={{ slotLabel: 'Micro Batch Size' }}
                    defaultValue={1}
                    min={1}
                    max={64}
                    step={1}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'automodel.optimizer.warmup_steps', control }}
                    formFieldProps={{ slotLabel: 'Warmup Steps' }}
                    defaultValue={0}
                    min={0}
                    max={1000}
                    step={1}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'automodel.optimizer.weight_decay', control }}
                    formFieldProps={{ slotLabel: 'Weight Decay' }}
                    defaultValue={0.01}
                    min={0}
                    max={1}
                    step={0.01}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'automodel.optimizer.min_learning_rate', control }}
                    formFieldProps={{ slotLabel: 'Min Learning Rate' }}
                    defaultValue={0}
                    min={0}
                    max={1e-3}
                    step={1e-6}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'automodel.optimizer.adam_eps', control }}
                    formFieldProps={{ slotLabel: 'Adam Epsilon' }}
                    defaultValue={1e-8}
                    min={1e-10}
                    max={1e-6}
                    step={1e-10}
                    disabled={disabled}
                  />
                  <ControlledSelect
                    useControllerProps={{ name: 'automodel.optimizer.optimizer', control }}
                    formFieldProps={{ slotLabel: 'Optimizer' }}
                    items={[
                      { value: 'Adam', children: 'Adam' },
                      { value: 'AdamW', children: 'AdamW' },
                    ]}
                    disabled={disabled}
                  />
                  <ControlledSelect
                    useControllerProps={{ name: 'automodel.optimizer.lr_decay_style', control }}
                    formFieldProps={{ slotLabel: 'LR Decay Style' }}
                    items={[
                      { value: 'cosine', children: 'Cosine' },
                      { value: 'linear', children: 'Linear' },
                      { value: 'constant', children: 'Constant' },
                    ]}
                    disabled={disabled}
                  />
                  <ControlledSelect
                    useControllerProps={{ name: 'automodel.training.attn_implementation', control }}
                    formFieldProps={{ slotLabel: 'Attention Implementation' }}
                    items={[
                      { value: 'sdpa', children: 'SDPA' },
                      { value: 'flash_attention_2', children: 'FlashAttention 2' },
                      { value: 'eager', children: 'Eager' },
                    ]}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{
                      name: 'automodel.batch.sequence_packing_max_samples',
                      control,
                    }}
                    formFieldProps={{ slotLabel: 'Sequence Packing Max Samples' }}
                    defaultValue={1000}
                    min={1}
                    max={10000}
                    step={1}
                    disabled={disabled}
                  />
                </Stack>
              </AccordionContent>
            </AccordionItem>
          </AccordionRoot>
        </Stack>
      </FormSection>
    );
  }

  return (
    <FormSection title="Training Parameters">
      <Stack gap="density-lg">
        <ControlledSliderWithTextInput
          useControllerProps={{ name: 'unsloth.schedule.epochs', control }}
          formFieldProps={{ slotLabel: 'Epochs' }}
          defaultValue={1}
          min={1}
          max={100}
          step={1}
          disabled={disabled}
        />
        <ControlledSliderWithTextInput
          useControllerProps={{ name: 'unsloth.optimizer.learning_rate', control }}
          formFieldProps={{ slotLabel: 'Learning Rate' }}
          defaultValue={2e-4}
          min={1e-6}
          max={1e-3}
          step={1e-6}
          disabled={disabled}
        />
        <ControlledSliderWithTextInput
          useControllerProps={{ name: 'unsloth.batch.per_device_train_batch_size', control }}
          formFieldProps={{ slotLabel: 'Per-Device Batch Size' }}
          defaultValue={1}
          min={1}
          max={64}
          step={1}
          disabled={disabled}
        />
        <ControlledSliderWithTextInput
          useControllerProps={{ name: 'unsloth.model.max_seq_length', control }}
          formFieldProps={{ slotLabel: 'Max Sequence Length' }}
          defaultValue={2048}
          min={128}
          max={131072}
          step={128}
          disabled={disabled}
        />
        <AccordionRoot multiple>
          <AccordionItem value="advanced">
            <AccordionTrigger>
              <Text kind="label/bold/md">Advanced</Text>
            </AccordionTrigger>
            <AccordionContent>
              <Stack gap="density-md" className="pt-density-md">
                <ControlledSliderWithTextInput
                  useControllerProps={{
                    name: 'unsloth.batch.gradient_accumulation_steps',
                    control,
                  }}
                  formFieldProps={{ slotLabel: 'Gradient Accumulation Steps' }}
                  defaultValue={1}
                  min={1}
                  max={64}
                  step={1}
                  disabled={disabled}
                />
                <ControlledSliderWithTextInput
                  useControllerProps={{ name: 'unsloth.schedule.warmup_steps', control }}
                  formFieldProps={{ slotLabel: 'Warmup Steps' }}
                  defaultValue={0}
                  min={0}
                  max={1000}
                  step={1}
                  disabled={disabled}
                />
                <ControlledSliderWithTextInput
                  useControllerProps={{ name: 'unsloth.optimizer.weight_decay', control }}
                  formFieldProps={{ slotLabel: 'Weight Decay' }}
                  defaultValue={0}
                  min={0}
                  max={1}
                  step={0.01}
                  disabled={disabled}
                />
                <ControlledSliderWithTextInput
                  useControllerProps={{ name: 'unsloth.optimizer.adam_beta1', control }}
                  formFieldProps={{ slotLabel: 'Adam Beta1' }}
                  defaultValue={0.9}
                  min={0}
                  max={1}
                  step={0.001}
                  disabled={disabled}
                />
                <ControlledSliderWithTextInput
                  useControllerProps={{ name: 'unsloth.optimizer.adam_beta2', control }}
                  formFieldProps={{ slotLabel: 'Adam Beta2' }}
                  defaultValue={0.999}
                  min={0}
                  max={1}
                  step={0.001}
                  disabled={disabled}
                />
                <ControlledSliderWithTextInput
                  useControllerProps={{ name: 'unsloth.optimizer.adam_epsilon', control }}
                  formFieldProps={{ slotLabel: 'Adam Epsilon' }}
                  defaultValue={1e-8}
                  min={1e-10}
                  max={1e-6}
                  step={1e-10}
                  disabled={disabled}
                />
                <ControlledSliderWithTextInput
                  useControllerProps={{ name: 'unsloth.optimizer.max_grad_norm', control }}
                  formFieldProps={{ slotLabel: 'Max Gradient Norm' }}
                  defaultValue={1}
                  min={0}
                  max={10}
                  step={0.1}
                  disabled={disabled}
                />
                <ControlledSliderWithTextInput
                  useControllerProps={{ name: 'unsloth.optimizer.label_smoothing_factor', control }}
                  formFieldProps={{ slotLabel: 'Label Smoothing Factor' }}
                  defaultValue={0}
                  min={0}
                  max={1}
                  step={0.01}
                  disabled={disabled}
                />
                <ControlledSliderWithTextInput
                  useControllerProps={{ name: 'unsloth.optimizer.neftune_noise_alpha', control }}
                  formFieldProps={{ slotLabel: 'NEFTune Noise Alpha' }}
                  defaultValue={0}
                  min={0}
                  max={20}
                  step={1}
                  disabled={disabled}
                />
                <ControlledJsonInput
                  useControllerProps={{ name: 'unsloth.schedule.lr_scheduler_kwargs', control }}
                  formFieldProps={{ slotLabel: 'LR Scheduler Kwargs (JSON)' }}
                  placeholder='{ "num_cycles": 1 }'
                  disabled={disabled}
                />
                <ControlledJsonInput
                  useControllerProps={{ name: 'unsloth.model.rope_scaling', control }}
                  formFieldProps={{ slotLabel: 'RoPE Scaling (JSON)' }}
                  placeholder='{ "type": "linear", "factor": 2.0 }'
                  disabled={disabled}
                />
              </Stack>
            </AccordionContent>
          </AccordionItem>
        </AccordionRoot>
      </Stack>
    </FormSection>
  );
};
