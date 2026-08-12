// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import { FORM_DEFAULTS, type CustomizationFormFields } from '@studio/util/forms/customization';

export interface CustomizationTemplateModel {
  hfRepoId: string;
  name: string;
  requiresHfToken: boolean;
  trustRemoteCode?: boolean;
}

export interface CustomizationTemplateDataset {
  hfDataset: string;
  hfConfig: string;
  hfSplit: string;
  trainingRowCount: number;
  validationRowCount: number;
  name: string;
  convertRow: (row: Record<string, unknown>) => Record<string, unknown> | null;
}

export interface CustomizationTemplate {
  id: string;
  title: string;
  description: string;
  trainingLabel: string;
  models: CustomizationTemplateModel[];
  dataset: CustomizationTemplateDataset;
  buildFormSpec: (workspace: string, datasetRef: string) => CustomizationFormFields;
}

/**
 * Settings every Nemotron cookbook shares, and that the platform cannot express.
 *
 * - Activation checkpointing. The Super and Ultra cookbooks set
 *   `activation_checkpointing: true`, Super noting it "avoids OOM on 80GB". The
 *   platform emits that key only for embedding models, and Automodel's own
 *   `FSDP2Config` defaults it to `False`, so these recipes train without it.
 * - Multi-token prediction (Ultra and Lightning cookbooks only):
 *   `num_nextn_predict_layers`, `mtp_use_repeated_layer`, `mtp_loss_scaling_factor`.
 * - The Transformer Engine / grouped-matmul / DeepEP backend block. The platform
 *   detects MoE itself and emits its own `BackendConfig`, deliberately with DeepEP
 *   disabled.
 *
 * Closing these needs fields on the automodel job schema plus emission in the
 * automodel service; they are not fixable from the frontend.
 */

/**
 * BIRD-SQL rows into prompt/completion pairs, matching the prompt layout in the
 * Nemotron text2SQL cookbook: the database DDL, then the question, then the
 * evidence hint. `evidence` is frequently empty upstream, so it is not required.
 */
const birdSqlConvertRow = (row: Record<string, unknown>): Record<string, unknown> | null => {
  const schema = typeof row.schema === 'string' ? row.schema : '';
  const question = typeof row.question === 'string' ? row.question : '';
  const evidence = typeof row.evidence === 'string' ? row.evidence : '';
  const sql = typeof row.SQL === 'string' ? row.SQL : '';
  if (!schema || !question || !sql) return null;
  return { prompt: `${schema}\n\n${question}\n${evidence}`, completion: sql };
};

export const CUSTOMIZATION_TEMPLATES: CustomizationTemplate[] = [
  {
    // Port of the NVIDIA Nemotron cookbook:
    // usage-cookbook/Nemotron-3-Super/lora-text2sql/nemo-automodel
    // Hyperparameters below mirror that recipe's base-peft-config-cookbook.yaml.
    id: 'lora-nemotron-3-super-text2sql',
    title: 'LoRA — Nemotron 3 Super (Text-to-SQL)',
    trainingLabel: 'LoRA',
    description:
      'Teach Nemotron 3 Super to write SQL from a database schema and a question, trained on BIRD-SQL. A mixture-of-experts model this size is impractical to configure by hand — this recipe ships the expert-parallel and LoRA settings from the NVIDIA cookbook. Targets one 8×80GB node; the cookbook also enables activation checkpointing to stay inside that budget, which the platform cannot yet set.',
    models: [
      {
        hfRepoId: 'nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16',
        name: 'nemotron-3-super-120b-a12b-bf16',
        // The cookbook tells you to `huggingface-cli login`, but the repo is not gated
        // (HF reports gated: false and config.json resolves unauthenticated). Requiring a
        // token here would block provisioning on an `hf-token` secret nobody needs.
        requiresHfToken: false,
        trustRemoteCode: true,
      },
    ],
    dataset: {
      hfDataset: 'xu3kev/BIRD-SQL-data-train',
      hfConfig: 'default',
      hfSplit: 'train',
      // The cookbook trains on the full BIRD train split. Each row embeds a complete
      // CREATE TABLE schema (~5KB), and these rows are fetched and converted in the
      // browser, so the template takes a slice: ~5.8MB instead of ~50MB.
      trainingRowCount: 1000,
      validationRowCount: 100,
      name: 'bird-sql-text2sql',
      convertRow: birdSqlConvertRow,
    },
    buildFormSpec: (workspace, datasetRef) => ({
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      backend: 'automodel',
      automodel: {
        ...FORM_DEFAULTS.automodel,
        model: `${workspace}/nemotron-3-super-120b-a12b-bf16`,
        dataset: { training: datasetRef, validation: datasetRef },
        training: {
          ...FORM_DEFAULTS.automodel.training,
          training_type: 'sft',
          finetuning_type: 'lora',
          lora: {
            rank: 8,
            alpha: 32,
            dropout: 0,
            merge: false,
            use_triton: true,
            // Nemotron's Mamba layers consume out_proj.weight directly through custom
            // kernels, so LoRA adapters on those modules are silently ineffective.
            exclude_modules: ['*.out_proj'],
          },
          max_seq_length: 4096,
          precision: 'bf16',
        },
        schedule: { ...FORM_DEFAULTS.automodel.schedule, epochs: 1 },
        // global 8 / micro 1 → grad accumulation of 8, the minimum-memory configuration
        // the cookbook uses to stay inside 80GB per GPU.
        batch: { ...FORM_DEFAULTS.automodel.batch, global_batch_size: 8, micro_batch_size: 1 },
        optimizer: {
          ...FORM_DEFAULTS.automodel.optimizer,
          learning_rate: 1e-5,
          min_learning_rate: 1e-6,
          weight_decay: 0,
          adam_beta1: 0.9,
          adam_beta2: 0.999,
          adam_eps: 1e-8,
          optimizer: 'Adam',
          lr_decay_style: 'cosine',
        },
        parallelism: {
          ...FORM_DEFAULTS.automodel.parallelism,
          num_nodes: 1,
          // ep_size=8 spans all 8 GPUs; tensor and expert parallelism share them.
          num_gpus_per_node: 8,
          tensor_parallel_size: 1,
          pipeline_parallel_size: 1,
          context_parallel_size: 1,
          expert_parallel_size: 8,
          sequence_parallel: false,
        },
      },
    }),
  },
  {
    // Port of usage-cookbook/Nemotron-3-Ultra/lora-text2sql/nemo-automodel,
    // nemotron_ultra_v3_text2sql_peft_h100.yaml (the validated 4-node H100 topology).
    //
    // Divergence: the cookbook also configures multi-token prediction
    // (num_nextn_predict_layers / mtp_use_repeated_layer / mtp_loss_scaling_factor)
    // and a FusedLinearCrossEntropy loss. Neither is expressible in the platform's
    // automodel job schema, so this trains without MTP.
    id: 'lora-nemotron-3-ultra-text2sql',
    title: 'LoRA — Nemotron 3 Ultra (Text-to-SQL)',
    trainingLabel: 'LoRA',
    description:
      'The 550B Text-to-SQL recipe from the Nemotron cookbook, on BIRD-SQL. Needs a 4-node, 32-GPU H100 allocation — expert parallelism spans every GPU. Trains without multi-token prediction, which the cookbook enables.',
    models: [
      {
        hfRepoId: 'nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16',
        name: 'nemotron-3-ultra-550b-a55b-bf16',
        requiresHfToken: false,
        trustRemoteCode: true,
      },
    ],
    dataset: {
      hfDataset: 'xu3kev/BIRD-SQL-data-train',
      hfConfig: 'default',
      hfSplit: 'train',
      trainingRowCount: 1000,
      validationRowCount: 100,
      name: 'bird-sql-text2sql',
      convertRow: birdSqlConvertRow,
    },
    buildFormSpec: (workspace, datasetRef) => ({
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      backend: 'automodel',
      automodel: {
        ...FORM_DEFAULTS.automodel,
        model: `${workspace}/nemotron-3-ultra-550b-a55b-bf16`,
        dataset: { training: datasetRef, validation: datasetRef },
        training: {
          ...FORM_DEFAULTS.automodel.training,
          training_type: 'sft',
          finetuning_type: 'lora',
          lora: {
            rank: 32,
            alpha: 32,
            dropout: 0,
            merge: false,
            use_triton: true,
            exclude_modules: ['*.out_proj'],
          },
          // The cookbook sets no dataset seq_length and packs to 2048 with the THD
          // strategy. Those are separate knobs there, but not here: the platform derives
          // pack size as min(estimate, max_seq_length), so a 2048 cap to match the pack
          // size would also truncate sequences. ~13% of BIRD-SQL rows exceed 2048 tokens
          // versus ~7% over 4096, and truncation drops the trailing SQL — the training
          // target. Matching the siblings at 4096 keeps the target intact; the cost is a
          // pack size that may exceed the cookbook's 2048.
          max_seq_length: 4096,
          precision: 'bf16',
        },
        schedule: { ...FORM_DEFAULTS.automodel.schedule, epochs: 1, max_steps: 100 },
        batch: {
          ...FORM_DEFAULTS.automodel.batch,
          global_batch_size: 128,
          micro_batch_size: 4,
          sequence_packing: true,
        },
        optimizer: {
          ...FORM_DEFAULTS.automodel.optimizer,
          learning_rate: 1e-4,
          min_learning_rate: 1e-5,
          weight_decay: 0.1,
          adam_beta1: 0.9,
          adam_beta2: 0.95,
          adam_eps: 1e-8,
          warmup_steps: 10,
          optimizer: 'AdamW',
          lr_decay_style: 'cosine',
        },
        parallelism: {
          ...FORM_DEFAULTS.automodel.parallelism,
          // ep_size must equal world size: 4 nodes x 8 GPUs = 32.
          num_nodes: 4,
          num_gpus_per_node: 8,
          tensor_parallel_size: 1,
          pipeline_parallel_size: 1,
          context_parallel_size: 1,
          expert_parallel_size: 32,
          sequence_parallel: false,
        },
      },
    }),
  },
  {
    // Hyperparameters from usage-cookbook/Nemotron-3.5-Lightning/lora-text2sql/
    // nemo-automodel, nemotron_mtp_lightning35_hellaswag_peft.yaml.
    //
    // Divergences: that cookbook trains on HellaSwag through automodel's built-in
    // dataset class, which the platform's fileset-based data path cannot use, so this
    // recipe applies the same BIRD-SQL Text-to-SQL task as its Super and Ultra
    // siblings. It also trains without the cookbook's multi-token prediction.
    id: 'lora-nemotron-35-lightning-text2sql',
    title: 'LoRA — Nemotron 3.5 Lightning (Text-to-SQL)',
    trainingLabel: 'LoRA',
    description:
      'The most approachable Nemotron mixture-of-experts recipe: 30B with 3B active, tuned on a single 8-GPU node. Uses the Lightning cookbook LoRA and optimizer settings, applied to BIRD-SQL Text-to-SQL.',
    models: [
      {
        hfRepoId: 'nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16',
        name: 'nemotron-35-lightning-30b-a3b-bf16',
        requiresHfToken: false,
        trustRemoteCode: true,
      },
    ],
    dataset: {
      hfDataset: 'xu3kev/BIRD-SQL-data-train',
      hfConfig: 'default',
      hfSplit: 'train',
      trainingRowCount: 1000,
      validationRowCount: 100,
      name: 'bird-sql-text2sql',
      convertRow: birdSqlConvertRow,
    },
    buildFormSpec: (workspace, datasetRef) => ({
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      backend: 'automodel',
      automodel: {
        ...FORM_DEFAULTS.automodel,
        model: `${workspace}/nemotron-35-lightning-30b-a3b-bf16`,
        dataset: { training: datasetRef, validation: datasetRef },
        training: {
          ...FORM_DEFAULTS.automodel.training,
          training_type: 'sft',
          finetuning_type: 'lora',
          lora: {
            rank: 8,
            alpha: 32,
            dropout: 0,
            merge: false,
            use_triton: true,
            exclude_modules: ['*.out_proj'],
          },
          max_seq_length: 4096,
          precision: 'bf16',
        },
        schedule: { ...FORM_DEFAULTS.automodel.schedule, epochs: 1, max_steps: 100 },
        // The cookbook sets packed_sequence_size: 0 — no packing.
        batch: {
          ...FORM_DEFAULTS.automodel.batch,
          global_batch_size: 8,
          micro_batch_size: 1,
          sequence_packing: false,
        },
        optimizer: {
          ...FORM_DEFAULTS.automodel.optimizer,
          learning_rate: 1e-4,
          min_learning_rate: 1e-5,
          weight_decay: 0.1,
          adam_beta1: 0.9,
          adam_beta2: 0.95,
          adam_eps: 1e-8,
          warmup_steps: 10,
          optimizer: 'AdamW',
          lr_decay_style: 'cosine',
        },
        parallelism: {
          ...FORM_DEFAULTS.automodel.parallelism,
          num_nodes: 1,
          num_gpus_per_node: 8,
          tensor_parallel_size: 1,
          pipeline_parallel_size: 1,
          context_parallel_size: 1,
          expert_parallel_size: 8,
          sequence_parallel: false,
        },
      },
    }),
  },
];
