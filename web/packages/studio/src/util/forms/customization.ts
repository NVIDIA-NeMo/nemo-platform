// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import {
  type AutomodelJobInput,
  type AutomodelJobsJobRequest,
  OptimizerType,
  RlGRPOTrainingFinetuningType,
  type RlDPOTraining,
  type RlGRPOTraining,
  type RlJobInput,
  type RlJobsJobRequest,
  type RlLoRAParams,
  type UnslothJobInput,
  type UnslothJobsJobRequest,
} from '@nemo/sdk/generated/customizer/schema';
import { CustomizationCreateAutomodelJobBody } from '@nemo/sdk/generated/customizer/zod/automodel-jobs';
import { CustomizationCreateRlJobBody } from '@nemo/sdk/generated/customizer/zod/rl-jobs';
import { CustomizationCreateUnslothJobBody } from '@nemo/sdk/generated/customizer/zod/unsloth-jobs';
import {
  CustomizationBackend,
  isAutomodelJob,
  isRlJob,
  type CustomizationJob,
} from '@studio/util/customizationBackend';
import type { TrainingType } from '@studio/util/customizerSchema';
import { z } from 'zod';

/**
 * The LoRA knobs the GRPO form exposes. `target_modules`/`exclude_modules` are left
 * to the backend, and the rest are required here because every control is always
 * rendered with a value.
 */
export type GrpoLoraFields = Required<
  Pick<RlLoRAParams, 'rank' | 'alpha' | 'dropout' | 'use_triton'>
>;

/**
 * GRPO-only hyperparameters, kept in their own namespace because `rl.training` holds
 * a single object shared with the DPO form. Derived from `RlGRPOTraining` so the form
 * cannot drift from the API — field docs come from the generated schema.
 */
export interface GrpoFormFields extends Required<
  Pick<
    RlGRPOTraining,
    | 'num_generations_per_prompt'
    | 'num_prompts_per_step'
    | 'max_rollout_turns'
    | 'normalize_rewards'
    | 'ratio_clip_min'
    | 'ratio_clip_max'
    | 'finetuning_type'
    | 'temperature'
    | 'val_at_start'
    | 'overlong_filtering'
  >
> {
  /** 'grpo' shows the GRPO form sections; 'dpo' shows DPO sections. Maps to training.type on submit. */
  trainingType: RlDPOTraining['type'] | RlGRPOTraining['type'];
  /** Fileset reference for the NeMo Gym reward environment. */
  environmentFileset: string;
  /**
   * Seeded to match the default `max_seq_length`, which is what the backend would
   * derive it from anyway. It has to carry a value because its slider needs a reset
   * target, and a reset target that differs from the form default is a control whose
   * ↺ silently changes the request. Raising Max Sequence Length does NOT raise this —
   * the two are set independently, and the backend rejects this exceeding that.
   */
  max_new_tokens: RlGRPOTraining['max_new_tokens'];
  /** LoRA hyperparameters; only sent when finetuning_type is 'lora'. */
  lora: GrpoLoraFields;
}

export interface CustomizationFormFields {
  backend: CustomizationBackend;
  outputName: string;
  description: string;
  automodel: AutomodelJobInput;
  unsloth: UnslothJobInput;
  rl: RlJobInput;
  grpo: GrpoFormFields;
}

type DatasetFieldName = 'automodel.dataset.training' | 'unsloth.dataset.path' | 'rl.dataset';

/** Each backend keeps the training dataset reference under a different path. */
export const DATASET_FIELD_BY_BACKEND: Record<CustomizationBackend, DatasetFieldName> = {
  automodel: 'automodel.dataset.training',
  unsloth: 'unsloth.dataset.path',
  rl: 'rl.dataset',
};

type ModelFieldName = 'automodel.model' | 'unsloth.model.name' | 'rl.model';

/** Likewise for the base model reference. */
export const MODEL_FIELD_BY_BACKEND: Record<CustomizationBackend, ModelFieldName> = {
  automodel: 'automodel.model',
  unsloth: 'unsloth.model.name',
  rl: 'rl.model',
};

/** Unsloth is SFT-only; automodel and RL each carry their own method selector. */
export const resolveTrainingType = (
  backend: CustomizationBackend,
  automodelTrainingType: CustomizationFormFields['automodel']['training']['training_type'],
  rlTrainingType: GrpoFormFields['trainingType'] | undefined
): TrainingType => {
  switch (backend) {
    case 'rl':
      return rlTrainingType ?? 'dpo';
    case 'automodel':
      return automodelTrainingType ?? 'sft';
    default:
      return 'sft';
  }
};

const UNSLOTH_DEFAULT_TARGET_MODULES = [
  'q_proj',
  'k_proj',
  'v_proj',
  'o_proj',
  'gate_proj',
  'up_proj',
  'down_proj',
];

const RL_DPO_DEFAULTS: RlJobInput = {
  model: '',
  dataset: '',
  training: {
    type: 'dpo',
    epochs: 1,
    learning_rate: 1e-4,
    batch_size: 32,
    micro_batch_size: 1,
    max_seq_length: 2048,
    warmup_steps: 0,
    weight_decay: 0.01,
    ref_policy_kl_penalty: 0.1,
    preference_loss_weight: 1,
    sft_loss_weight: 0,
    preference_average_log_probs: false,
    sft_average_log_probs: false,
    parallelism: {
      num_nodes: 1,
      num_gpus_per_node: 1,
      tensor_parallel_size: 1,
      pipeline_parallel_size: 1,
      context_parallel_size: 1,
      sequence_parallel: false,
    },
  },
};

/** Fields both RL forms bind to. `RL_DPO_DEFAULTS.training` is `RlDPOTraining` and omits them. */
const RL_SHARED_TRAINING_DEFAULTS = {
  optimizer_type: OptimizerType.adamw_with_cosine_annealing,
  min_learning_rate: 0,
  adam_beta1: 0.9,
  adam_beta2: 0.999,
  adam_eps: 1e-8,
  max_grad_norm: 1.0,
  seed: 42,
  val_check_interval: 1.0,
  keep_top_k: 1,
  activation_checkpointing: false,
};

/**
 * `rl.training` is shared by the DPO and GRPO forms, so each method's defaults must
 * stand alone — a GRPO seed left here would silently override the backend for DPO.
 * DPO matches the backend (`max_steps: None`, `val_at_end: True`); GRPO runs to a
 * step budget and skips the trailing validation pass.
 *
 * The casts are required: spreading `RlDPOTraining` with GRPO-only fields yields an
 * object valid for either arm, but TS will not infer the discriminated union itself.
 */
export const RL_DPO_TRAINING_DEFAULTS = {
  ...RL_DPO_DEFAULTS.training,
  ...RL_SHARED_TRAINING_DEFAULTS,
  val_at_end: true,
} as RlJobInput['training'];

export const RL_GRPO_TRAINING_DEFAULTS = {
  ...RL_DPO_DEFAULTS.training,
  ...RL_SHARED_TRAINING_DEFAULTS,
  max_steps: 500,
  val_at_end: false,
  // Backend default is 0.0 for GRPO and 0.05 for DPO; the 0.1 inherited from
  // RL_DPO_DEFAULTS would otherwise apply a KL penalty the user never asked for.
  ref_policy_kl_penalty: 0.0,
} as RlJobInput['training'];

export const FORM_DEFAULTS: CustomizationFormFields = {
  backend: 'automodel',
  outputName: '',
  description: '',
  automodel: {
    model: '',
    dataset: { training: '' },
    training: {
      training_type: 'sft',
      finetuning_type: 'lora',
      lora: { rank: 16, alpha: 32, dropout: 0, merge: false, use_triton: true },
      max_seq_length: 2048,
      attn_implementation: 'sdpa',
    },
    schedule: { epochs: 1 },
    batch: { global_batch_size: 8, micro_batch_size: 1, sequence_packing: false },
    optimizer: {
      learning_rate: 5e-6,
      weight_decay: 0.01,
      warmup_steps: 0,
      adam_beta1: 0.9,
      adam_beta2: 0.999,
      optimizer: 'Adam',
      lr_decay_style: 'cosine',
    },
    parallelism: {
      num_nodes: 1,
      num_gpus_per_node: 1,
      tensor_parallel_size: 1,
      pipeline_parallel_size: 1,
      context_parallel_size: 1,
      sequence_parallel: false,
    },
  },
  unsloth: {
    model: {
      name: '',
      max_seq_length: 2048,
      load_in_4bit: true,
      load_in_8bit: false,
      dtype: 'auto',
      trust_remote_code: false,
    },
    dataset: {
      path: '',
      text_field: 'text',
      apply_chat_template: false,
      packing: false,
    },
    training: {
      training_type: 'sft',
      finetuning_type: 'lora',
      lora: {
        rank: 16,
        alpha: 16,
        dropout: 0,
        target_modules: UNSLOTH_DEFAULT_TARGET_MODULES,
        bias: 'none',
        use_rslora: false,
        random_state: 3407,
        init_lora_weights: true,
      },
      use_gradient_checkpointing: 'unsloth',
    },
    schedule: {
      epochs: 1,
      warmup_steps: 0,
      lr_scheduler_type: 'linear',
      logging_steps: 1,
      seed: 3407,
    },
    batch: { per_device_train_batch_size: 1, gradient_accumulation_steps: 1 },
    optimizer: { learning_rate: 2e-4, weight_decay: 0, optim: 'adamw_8bit' },
    hardware: { precision: 'bf16' },
  },
  rl: {
    ...RL_DPO_DEFAULTS,
    training: RL_DPO_TRAINING_DEFAULTS,
  },
  grpo: {
    trainingType: 'dpo',
    environmentFileset: '',
    num_generations_per_prompt: 8,
    num_prompts_per_step: 8,
    overlong_filtering: false,
    max_rollout_turns: 1,
    normalize_rewards: true,
    ratio_clip_min: 0.2,
    ratio_clip_max: 0.28,
    temperature: 1.0,
    val_at_start: false,
    max_new_tokens: 2048,
    finetuning_type: RlGRPOTrainingFinetuningType.all_weights,
    lora: { rank: 16, alpha: 32, dropout: 0, use_triton: true },
  },
};

const automodelBodySpec = CustomizationCreateAutomodelJobBody.shape.spec;
const automodelSpecSchema = automodelBodySpec
  .omit({ output: true })
  .extend({
    model: z.string().min(1, 'Please select a model'),
    dataset: automodelBodySpec.shape.dataset.extend({
      training: z.string().min(1, 'Training dataset is required'),
    }),
  })
  .superRefine((spec, ctx) => {
    if (spec.training.training_type === 'distillation' && !spec.training.teacher_model) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Teacher model is required for distillation',
        path: ['training', 'teacher_model'],
      });
    }
  });

const unslothBodySpec = CustomizationCreateUnslothJobBody.shape.spec;
const unslothSpecSchema = unslothBodySpec.omit({ output: true }).extend({
  model: unslothBodySpec.shape.model.extend({
    name: z.string().min(1, 'Please select a model'),
  }),
  dataset: unslothBodySpec.shape.dataset.extend({
    path: z.string().min(1, 'Training dataset is required'),
  }),
});

const rlBodySpec = CustomizationCreateRlJobBody.shape.spec;
const rlSpecSchema = rlBodySpec.omit({ output: true }).extend({
  model: z.string().min(1, 'Please select a model'),
  dataset: z.string().min(1, 'Training dataset is required'),
});

export const customizationFormSchema = z
  .object({
    backend: z.nativeEnum(CustomizationBackend),
    outputName: z.string().min(1, 'Output model name is required'),
    description: z.string(),
    automodel: z.unknown(),
    unsloth: z.unknown(),
    rl: z.unknown(),
    grpo: z.unknown(),
  })
  .superRefine((data, ctx) => {
    let spec: z.ZodTypeAny;
    let value: unknown;
    if (data.backend === 'automodel') {
      spec = automodelSpecSchema;
      value = data.automodel;
    } else if (data.backend === 'unsloth') {
      spec = unslothSpecSchema;
      value = data.unsloth;
    } else {
      spec = rlSpecSchema;
      value = data.rl;
      const grpo = data.grpo as Partial<GrpoFormFields> | undefined;
      if (grpo?.trainingType === 'grpo') {
        if (!grpo.environmentFileset) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: 'A reward environment fileset is required for GRPO training',
            path: ['grpo', 'environmentFileset'],
          });
        }
        // Mirrors the backend's _generation_length_fits_context validator: max_seq_length
        // is the whole prompt + generation budget, so a larger generation cap is
        // unsatisfiable and the job is rejected at submit.
        const maxSeqLength = (data.rl as RlJobInput | undefined)?.training?.max_seq_length;
        if (
          grpo.max_new_tokens != null &&
          maxSeqLength != null &&
          grpo.max_new_tokens > maxSeqLength
        ) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `Max new tokens cannot exceed the max sequence length (${maxSeqLength}), which is the total prompt + generation budget`,
            path: ['grpo', 'max_new_tokens'],
          });
        }
      }
    }
    const result = spec.safeParse(value);
    if (!result.success) {
      for (const issue of result.error.issues) {
        ctx.addIssue({ ...issue, path: [data.backend, ...issue.path] });
      }
    }
  });

export const formToAutomodelCreate = (f: CustomizationFormFields): AutomodelJobsJobRequest => {
  const { training } = f.automodel;
  const usesLora =
    training.finetuning_type === 'lora' || training.finetuning_type === 'lora_merged';
  const isDistillation = training.training_type === 'distillation';
  return {
    name: f.outputName || undefined,
    description: f.description || undefined,
    spec: {
      ...f.automodel,
      training: {
        ...training,
        lora: usesLora ? training.lora : undefined,
        teacher_model: isDistillation ? training.teacher_model || undefined : undefined,
      },
      output: { name: f.outputName, description: f.description || undefined },
    },
  };
};

export const formToRlCreate = (f: CustomizationFormFields): RlJobsJobRequest => {
  if (f.grpo.trainingType === 'grpo') {
    const t = f.rl.training;
    const isLora = f.grpo.finetuning_type === RlGRPOTrainingFinetuningType.lora;
    return {
      name: f.outputName || undefined,
      description: f.description || undefined,
      spec: {
        model: f.rl.model,
        dataset: f.rl.dataset,
        environment: f.grpo.environmentFileset || undefined,
        training: {
          type: 'grpo',
          optimizer_type: t.optimizer_type,
          learning_rate: t.learning_rate,
          min_learning_rate: t.min_learning_rate,
          weight_decay: t.weight_decay,
          adam_beta1: t.adam_beta1,
          adam_beta2: t.adam_beta2,
          adam_eps: t.adam_eps,
          warmup_steps: t.warmup_steps,
          max_steps: t.max_steps,
          val_check_interval: t.val_check_interval,
          val_at_end: t.val_at_end,
          keep_top_k: t.keep_top_k,
          batch_size: t.batch_size,
          micro_batch_size: t.micro_batch_size,
          activation_checkpointing: t.activation_checkpointing,
          max_seq_length: t.max_seq_length,
          seed: t.seed,
          parallelism: t.parallelism,
          max_grad_norm: t.max_grad_norm,
          finetuning_type: f.grpo.finetuning_type,
          lora: isLora ? f.grpo.lora : undefined,
          num_generations_per_prompt: f.grpo.num_generations_per_prompt,
          num_prompts_per_step: f.grpo.num_prompts_per_step,
          overlong_filtering: f.grpo.overlong_filtering,
          temperature: f.grpo.temperature,
          max_new_tokens: f.grpo.max_new_tokens,
          val_at_start: f.grpo.val_at_start,
          normalize_rewards: f.grpo.normalize_rewards,
          max_rollout_turns: f.grpo.max_rollout_turns,
          ref_policy_kl_penalty: t.ref_policy_kl_penalty,
          ratio_clip_min: f.grpo.ratio_clip_min,
          ratio_clip_max: f.grpo.ratio_clip_max,
        },
        output: { name: f.outputName || undefined },
      },
    };
  }

  // Explicitly pick the DPO-form-exposed fields rather than spreading, so a field the
  // GRPO form binds to can never leak into a DPO request. Every control rendered by
  // GeneralParametersSection's `rl` branch and DpoParametersSection must appear here —
  // anything omitted is a control the user can change that the request then ignores.
  const dpo = f.rl.training as RlDPOTraining;
  return {
    name: f.outputName || undefined,
    description: f.description || undefined,
    spec: {
      model: f.rl.model,
      dataset: f.rl.dataset,
      training: {
        type: 'dpo' as const,
        optimizer_type: dpo.optimizer_type,
        learning_rate: dpo.learning_rate,
        min_learning_rate: dpo.min_learning_rate,
        weight_decay: dpo.weight_decay,
        adam_beta1: dpo.adam_beta1,
        adam_beta2: dpo.adam_beta2,
        adam_eps: dpo.adam_eps,
        warmup_steps: dpo.warmup_steps,
        epochs: dpo.epochs,
        max_steps: dpo.max_steps,
        val_check_interval: dpo.val_check_interval,
        val_at_end: dpo.val_at_end,
        keep_top_k: dpo.keep_top_k,
        batch_size: dpo.batch_size,
        micro_batch_size: dpo.micro_batch_size,
        activation_checkpointing: dpo.activation_checkpointing,
        max_seq_length: dpo.max_seq_length,
        seed: dpo.seed,
        parallelism: dpo.parallelism,
        max_grad_norm: dpo.max_grad_norm,
        ref_policy_kl_penalty: dpo.ref_policy_kl_penalty,
        preference_loss_weight: dpo.preference_loss_weight,
        sft_loss_weight: dpo.sft_loss_weight,
        preference_average_log_probs: dpo.preference_average_log_probs,
        sft_average_log_probs: dpo.sft_average_log_probs,
      },
      output: { name: f.outputName || undefined },
    },
  };
};

export const formToUnslothCreate = (f: CustomizationFormFields): UnslothJobsJobRequest => {
  const { training } = f.unsloth;
  const usesLora = training?.finetuning_type === 'lora';
  return {
    name: f.outputName || undefined,
    description: f.description || undefined,
    spec: {
      ...f.unsloth,
      model: usesLora
        ? f.unsloth.model
        : { ...f.unsloth.model, load_in_4bit: false, load_in_8bit: false },
      hardware: { ...f.unsloth.hardware, gpus: f.unsloth.hardware?.gpus || undefined },
      training: training && { ...training, lora: usesLora ? training.lora : undefined },
      output: { name: f.outputName || undefined, description: f.description || undefined },
    },
  };
};

const stripNulls = <T>(value: T): T => {
  if (value === null) return undefined as unknown as T;
  if (Array.isArray(value)) return value.map(stripNulls) as unknown as T;
  if (typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, stripNulls(v)])
    ) as T;
  }
  return value;
};

export const jobToFormFields = (job: CustomizationJob): CustomizationFormFields => {
  if (isAutomodelJob(job)) {
    return {
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      description: job.description ?? '',
      backend: 'automodel',
      automodel: stripNulls(job.spec) as AutomodelJobInput,
    };
  }
  if (isRlJob(job)) {
    const spec = stripNulls(job.spec) as RlJobInput;
    // GRPO-only hyperparameters live in the `grpo` namespace, not on spec.training,
    // so replaying the spec alone would present a cloned GRPO job as a default DPO one.
    const grpo = spec.training.type === 'grpo' ? spec.training : undefined;
    const defaults = FORM_DEFAULTS.grpo;
    return {
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      description: job.description ?? '',
      backend: 'rl',
      rl: spec,
      grpo: {
        ...defaults,
        trainingType: grpo ? 'grpo' : 'dpo',
        environmentFileset: spec.environment ?? '',
        ...(grpo && {
          num_generations_per_prompt:
            grpo.num_generations_per_prompt ?? defaults.num_generations_per_prompt,
          num_prompts_per_step: grpo.num_prompts_per_step ?? defaults.num_prompts_per_step,
          overlong_filtering: grpo.overlong_filtering ?? defaults.overlong_filtering,
          max_rollout_turns: grpo.max_rollout_turns ?? defaults.max_rollout_turns,
          normalize_rewards: grpo.normalize_rewards ?? defaults.normalize_rewards,
          ratio_clip_min: grpo.ratio_clip_min ?? defaults.ratio_clip_min,
          ratio_clip_max: grpo.ratio_clip_max ?? defaults.ratio_clip_max,
          temperature: grpo.temperature ?? defaults.temperature,
          val_at_start: grpo.val_at_start ?? defaults.val_at_start,
          max_new_tokens: grpo.max_new_tokens ?? defaults.max_new_tokens,
          finetuning_type: grpo.finetuning_type ?? defaults.finetuning_type,
          lora: grpo.lora ? { ...defaults.lora, ...grpo.lora } : defaults.lora,
        }),
      },
    };
  }
  return {
    ...FORM_DEFAULTS,
    outputName: generateDefaultName(),
    description: job.description ?? '',
    backend: 'unsloth',
    unsloth: stripNulls(job.spec) as UnslothJobInput,
  };
};
