// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ControlledSelect } from '@nemo/common/src/components/form/ControlledSelect';
import { ControlledSliderWithTextInput } from '@nemo/common/src/components/form/ControlledSliderWithTextInput';
import { ControlledSwitch } from '@nemo/common/src/components/form/ControlledSwitch';
import { RadioCard } from '@nemo/common/src/components/RadioCard';
import { RlGRPOTrainingFinetuningType } from '@nemo/sdk/generated/customizer/schema';
import {
  AccordionContent,
  AccordionItem,
  AccordionRoot,
  AccordionTrigger,
  Divider,
  RadioGroupRoot,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { OPTIMIZER_TYPE_ITEMS } from '@studio/components/NewCustomizationForm/constants';
import { FormSection } from '@studio/components/NewCustomizationForm/FormSection';
import type { CustomizationFormFields } from '@studio/util/forms/customization';
import { useFormContext } from 'react-hook-form';

/** GRPO supports full-weight and LoRA only — lora_merged is rejected by the backend. */
const GRPO_FINETUNING_TYPES = [
  {
    value: RlGRPOTrainingFinetuningType.all_weights,
    title: 'Full Weights',
    description: 'Train all model parameters.',
  },
  {
    value: RlGRPOTrainingFinetuningType.lora,
    title: 'LoRA',
    description: 'Low-rank adapter — fewer parameters, less VRAM.',
  },
] as const;

export const GrpoParametersSection = () => {
  const { control, watch, setValue, formState } = useFormContext<CustomizationFormFields>();
  const disabled = formState.isSubmitting;
  const finetuningType = watch('grpo.finetuning_type');
  const isLora = finetuningType === RlGRPOTrainingFinetuningType.lora;

  return (
    <>
      <FormSection title="Rollout & Reward">
        <Stack gap="density-lg">
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'rl.training.max_seq_length', control }}
            formFieldProps={{
              slotLabel: 'Max Sequence Length',
              slotInfo: 'Maximum token length for training sequences, including rollout context.',
            }}
            defaultValue={2048}
            min={128}
            max={131072}
            step={128}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'grpo.num_generations_per_prompt', control }}
            formFieldProps={{
              slotLabel: 'Rollouts per Prompt',
              slotInfo:
                'Group size: number of responses sampled per prompt. Larger groups give more stable advantage estimates at higher memory cost.',
            }}
            defaultValue={8}
            min={1}
            max={64}
            step={1}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'grpo.num_prompts_per_step', control }}
            formFieldProps={{
              slotLabel: 'Prompts per Step',
              slotInfo:
                'Number of prompts sampled per training step. Must satisfy: prompts_per_step × rollouts_per_prompt is a multiple of the global batch size.',
            }}
            defaultValue={8}
            min={1}
            max={256}
            step={1}
            disabled={disabled}
          />
          <ControlledSwitch
            useControllerProps={{ name: 'grpo.overlong_filtering', control }}
            formFieldProps={{
              slotLabel: 'Drop Truncated Rollouts',
              labelPosition: 'left',
              slotInfo:
                'Zero the loss contribution of rollouts cut off by the generation limit, so the policy is not penalised for responses it never got to finish. Worth enabling when a low Max New Tokens truncates many rollouts. NeMo RL key: overlong_filtering.',
            }}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'grpo.max_rollout_turns', control }}
            formFieldProps={{
              slotLabel: 'Max Rollout Turns',
              slotInfo: 'Maximum agent turns per rollout. Single-turn environments use 1.',
            }}
            defaultValue={1}
            min={1}
            max={20}
            step={1}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'grpo.temperature', control }}
            formFieldProps={{
              slotLabel: 'Temperature',
              slotInfo:
                'Sampling temperature for rollout generation. Must stay above 0 — GRPO learns from the spread of rewards within a prompt group, and greedy sampling makes every rollout identical, so the spread is zero and the run does nothing. Applies to validation rollouts too. NeMo RL key: temperature.',
            }}
            defaultValue={1.0}
            min={0.05}
            max={2}
            step={0.05}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'grpo.max_new_tokens', control }}
            formFieldProps={{
              slotLabel: 'Max New Tokens',
              slotInfo:
                'Cap on tokens generated per rollout turn. Defaults to the max sequence length, letting a rollout run until the context is exhausted; lower it to bound response length and rollout duration. Cannot exceed max sequence length. NeMo RL key: max_new_tokens.',
            }}
            defaultValue={2048}
            min={1}
            max={131072}
            step={128}
            disabled={disabled}
          />
        </Stack>
      </FormSection>
      <Divider />
      <FormSection title="Training Parameters">
        <Stack gap="density-lg">
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
            useControllerProps={{ name: 'rl.training.ref_policy_kl_penalty', control }}
            formFieldProps={{
              slotLabel: 'KL Penalty',
              slotInfo:
                'KL penalty coefficient against the reference policy. Higher values keep the model closer to the reference.',
            }}
            defaultValue={0.0}
            min={0}
            max={1}
            step={0.01}
            disabled={disabled}
          />
          <ControlledSliderWithTextInput
            useControllerProps={{ name: 'rl.training.max_steps', control }}
            formFieldProps={{
              slotLabel: 'Max Steps',
              slotInfo: 'Maximum training steps. Overrides epochs when set.',
            }}
            defaultValue={500}
            min={1}
            max={10000}
            step={1}
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
          <AccordionRoot multiple>
            <AccordionItem value="advanced-grpo" className="border-b-0">
              <AccordionTrigger>
                <Text kind="label/bold/md">Advanced</Text>
              </AccordionTrigger>
              <AccordionContent>
                <Stack gap="density-md" className="pt-density-md">
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
                    useControllerProps={{ name: 'grpo.ratio_clip_min', control }}
                    formFieldProps={{
                      slotLabel: 'Clip Min',
                      slotInfo: 'Lower bound for PPO-style importance ratio clipping.',
                    }}
                    defaultValue={0.2}
                    min={0}
                    max={1}
                    step={0.01}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'grpo.ratio_clip_max', control }}
                    formFieldProps={{
                      slotLabel: 'Clip Max',
                      slotInfo: 'Upper bound for PPO-style importance ratio clipping.',
                    }}
                    defaultValue={0.28}
                    min={0}
                    max={2}
                    step={0.01}
                    disabled={disabled}
                  />
                  <ControlledSwitch
                    useControllerProps={{ name: 'grpo.normalize_rewards', control }}
                    formFieldProps={{
                      slotLabel: 'Normalize Rewards',
                      labelPosition: 'left',
                      slotInfo:
                        'Normalize rewards within each prompt group before computing advantages.',
                    }}
                    disabled={disabled}
                  />
                  <ControlledSliderWithTextInput
                    useControllerProps={{ name: 'rl.training.max_grad_norm', control }}
                    formFieldProps={{
                      slotLabel: 'Max Gradient Norm',
                      slotInfo: 'Gradient clipping threshold.',
                    }}
                    defaultValue={1.0}
                    min={0}
                    max={10}
                    step={0.1}
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
                      slotLabel: 'Evaluate every N steps',
                      slotInfo:
                        'GRPO validation is a scored rollout pass, not a loss computation. Values ≤ 1.0 are a fraction of an epoch; values > 1.0 are a step count. NeMo RL key: val_check_interval.',
                    }}
                    defaultValue={1.0}
                    min={0.01}
                    max={10}
                    step={0.01}
                    disabled={disabled}
                  />
                  <ControlledSwitch
                    useControllerProps={{ name: 'grpo.val_at_start', control }}
                    formFieldProps={{
                      slotLabel: 'Validate at Start',
                      labelPosition: 'left',
                      slotInfo:
                        'Run a validation pass before the first training step, so the baseline and the trained result come from one job on the same data. Off by default because a GRPO baseline costs a full rollout pass. NeMo RL key: val_at_start.',
                    }}
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
      <Divider />
      <FormSection title="Parameter Efficiency">
        <Stack gap="density-lg">
          <Stack gap="density-md">
            <Text kind="label/bold/md">Finetuning Type</Text>
            <RadioGroupRoot
              name="grpoFinetuningType"
              value={finetuningType ?? RlGRPOTrainingFinetuningType.all_weights}
              onValueChange={(v) =>
                setValue('grpo.finetuning_type', v as RlGRPOTrainingFinetuningType, {
                  shouldValidate: true,
                })
              }
              className="w-full"
              disabled={disabled}
            >
              <div className="grid grid-cols-2 gap-4">
                {GRPO_FINETUNING_TYPES.map((opt) => (
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
          {isLora && (
            <Stack gap="density-lg">
              <ControlledSliderWithTextInput
                useControllerProps={{ name: 'grpo.lora.rank', control }}
                formFieldProps={{ slotLabel: 'LoRA Rank' }}
                defaultValue={16}
                min={1}
                max={256}
                step={1}
                disabled={disabled}
              />
              <ControlledSliderWithTextInput
                useControllerProps={{ name: 'grpo.lora.alpha', control }}
                formFieldProps={{
                  slotLabel: 'LoRA Alpha',
                  slotInfo: 'Scaling factor; effective LR multiplier = alpha / rank.',
                }}
                defaultValue={32}
                min={1}
                max={512}
                step={1}
                disabled={disabled}
              />
              <ControlledSliderWithTextInput
                useControllerProps={{ name: 'grpo.lora.dropout', control }}
                formFieldProps={{ slotLabel: 'LoRA Dropout' }}
                defaultValue={0}
                min={0}
                max={1}
                step={0.01}
                disabled={disabled}
              />
              <ControlledSwitch
                useControllerProps={{ name: 'grpo.lora.use_triton', control }}
                formFieldProps={{
                  slotLabel: 'Use Triton Kernels',
                  labelPosition: 'left',
                  slotInfo:
                    'DTensor v2 Triton LoRA kernels. Disable when tensor_parallel_size > 1.',
                }}
                disabled={disabled}
              />
            </Stack>
          )}
        </Stack>
      </FormSection>
    </>
  );
};
