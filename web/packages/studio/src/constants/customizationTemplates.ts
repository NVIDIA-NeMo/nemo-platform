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

const DEFAULT_LORA = { rank: 16, alpha: 32, dropout: 0, merge: false, use_triton: true } as const;

const squadConvertRow = (row: Record<string, unknown>): Record<string, unknown> | null => {
  const answers = row.answers as { text?: string[] } | undefined;
  const completion = answers?.text?.[0];
  if (!completion) return null;
  return {
    prompt: `Context: ${row.context} Question: ${row.question} Answer:`,
    completion,
  };
};

const specterConvertRow = (row: Record<string, unknown>): Record<string, unknown> | null => {
  const set = row.set as string[] | undefined;
  if (!set?.[0] || !set[1] || !set[2]) return null;
  return { query: set[0], pos_doc: set[1], neg_doc: [set[2]] };
};

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
      'Teach Nemotron 3 Super to write SQL from a database schema and a question, trained on BIRD-SQL. A mixture-of-experts model this size is impractical to tune by hand — this recipe ships the expert-parallel and LoRA settings that make it fit on one 8×80GB node. Requires HF token.',
    models: [
      {
        hfRepoId: 'nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16',
        name: 'nemotron-3-super-120b-a12b-bf16',
        requiresHfToken: true,
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
          weight_decay: 0,
          adam_beta1: 0.9,
          adam_beta2: 0.999,
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
    id: 'lora-qwen3',
    title: 'LoRA — Qwen3-0.6B',
    trainingLabel: 'LoRA',
    description:
      'Fine-tune Qwen3-0.6B to answer questions from context passages, trained on SQuAD. Uses LoRA to update a small fraction of weights — fast and memory-efficient.',
    models: [{ hfRepoId: 'Qwen/Qwen3-0.6B', name: 'qwen3-0.6b', requiresHfToken: false }],
    dataset: {
      hfDataset: 'rajpurkar/squad',
      hfConfig: 'plain_text',
      hfSplit: 'train',
      trainingRowCount: 3000,
      validationRowCount: 300,
      name: 'sft-dataset',
      convertRow: squadConvertRow,
    },
    buildFormSpec: (workspace, datasetRef) => ({
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      backend: 'automodel',
      automodel: {
        ...FORM_DEFAULTS.automodel,
        model: `${workspace}/qwen3-0.6b`,
        dataset: { training: datasetRef, validation: datasetRef },
        training: {
          ...FORM_DEFAULTS.automodel.training,
          training_type: 'sft',
          finetuning_type: 'lora',
          lora: DEFAULT_LORA,
        },
        schedule: { ...FORM_DEFAULTS.automodel.schedule, epochs: 2 },
        batch: { ...FORM_DEFAULTS.automodel.batch, global_batch_size: 64, micro_batch_size: 1 },
        optimizer: { ...FORM_DEFAULTS.automodel.optimizer, learning_rate: 5e-5 },
      },
    }),
  },
  {
    id: 'sft-llama',
    title: 'Full SFT — Llama-3.2-1B',
    trainingLabel: 'Full SFT',
    description:
      'Fine-tune Llama-3.2-1B for question answering on SQuAD. Updates all model weights for maximum customization — best when LoRA underfits. Requires HF token.',
    models: [
      {
        hfRepoId: 'meta-llama/Llama-3.2-1B-Instruct',
        name: 'llama-3-2-1b-base',
        requiresHfToken: true,
      },
    ],
    dataset: {
      hfDataset: 'rajpurkar/squad',
      hfConfig: 'plain_text',
      hfSplit: 'train',
      trainingRowCount: 3000,
      validationRowCount: 300,
      name: 'sft-dataset',
      convertRow: squadConvertRow,
    },
    buildFormSpec: (workspace, datasetRef) => ({
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      backend: 'automodel',
      automodel: {
        ...FORM_DEFAULTS.automodel,
        model: `${workspace}/llama-3-2-1b-base`,
        dataset: { training: datasetRef, validation: datasetRef },
        training: {
          ...FORM_DEFAULTS.automodel.training,
          training_type: 'sft',
          finetuning_type: 'all_weights',
          lora: undefined,
        },
        schedule: { ...FORM_DEFAULTS.automodel.schedule, epochs: 2 },
        batch: { ...FORM_DEFAULTS.automodel.batch, global_batch_size: 64, micro_batch_size: 1 },
        optimizer: { ...FORM_DEFAULTS.automodel.optimizer, learning_rate: 5e-5 },
      },
    }),
  },
  {
    id: 'distillation-llama',
    title: 'Distillation — Llama 3B → 1B',
    trainingLabel: 'Distillation',
    description:
      "Get a 1B Llama to answer SQuAD questions nearly as well as the 3B version, at half the inference cost. The student learns by matching the teacher's output distribution. Requires HF token.",
    models: [
      {
        hfRepoId: 'meta-llama/Llama-3.2-1B-Instruct',
        name: 'llama-3-2-1b-student',
        requiresHfToken: true,
      },
      {
        hfRepoId: 'meta-llama/Llama-3.2-3B-Instruct',
        name: 'llama-3-2-3b-teacher',
        requiresHfToken: true,
      },
    ],
    dataset: {
      hfDataset: 'rajpurkar/squad',
      hfConfig: 'plain_text',
      hfSplit: 'train',
      trainingRowCount: 3000,
      validationRowCount: 300,
      name: 'kd-dataset',
      convertRow: squadConvertRow,
    },
    buildFormSpec: (workspace, datasetRef) => ({
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      backend: 'automodel',
      automodel: {
        ...FORM_DEFAULTS.automodel,
        model: `${workspace}/llama-3-2-1b-student`,
        dataset: { training: datasetRef, validation: datasetRef },
        training: {
          ...FORM_DEFAULTS.automodel.training,
          training_type: 'distillation',
          finetuning_type: 'all_weights',
          teacher_model: `${workspace}/llama-3-2-3b-teacher`,
          teacher_precision: 'bf16',
          distillation_ratio: 0.5,
          distillation_temperature: 2,
          lora: undefined,
        },
        schedule: { ...FORM_DEFAULTS.automodel.schedule, epochs: 1 },
        batch: { ...FORM_DEFAULTS.automodel.batch, global_batch_size: 64, micro_batch_size: 1 },
        optimizer: { ...FORM_DEFAULTS.automodel.optimizer, learning_rate: 5e-5 },
      },
    }),
  },
  {
    id: 'embedding-nemotron',
    title: 'Embedding — Nemotron-Embed-1B',
    trainingLabel: 'Embedding',
    description:
      'Fine-tune Nemotron-Embed-1B to retrieve relevant scientific papers, trained on SPECTER citation triplets. Uses full-weight tuning to adapt the embedding space to your domain.',
    models: [
      {
        hfRepoId: 'nvidia/llama-nemotron-embed-1b-v2',
        name: 'nv-nemotron-embed-1b-base',
        requiresHfToken: false,
        trustRemoteCode: true,
      },
    ],
    dataset: {
      hfDataset: 'embedding-data/SPECTER',
      hfConfig: 'default',
      hfSplit: 'train',
      trainingRowCount: 3000,
      validationRowCount: 150,
      name: 'embedding-dataset',
      convertRow: specterConvertRow,
    },
    buildFormSpec: (workspace, datasetRef) => ({
      ...FORM_DEFAULTS,
      outputName: generateDefaultName(),
      backend: 'automodel',
      automodel: {
        ...FORM_DEFAULTS.automodel,
        model: `${workspace}/nv-nemotron-embed-1b-base`,
        dataset: { training: datasetRef, validation: datasetRef },
        training: {
          ...FORM_DEFAULTS.automodel.training,
          training_type: 'sft',
          finetuning_type: 'all_weights',
          lora: undefined,
          max_seq_length: 512,
        },
        schedule: { ...FORM_DEFAULTS.automodel.schedule, epochs: 1 },
        batch: { ...FORM_DEFAULTS.automodel.batch, global_batch_size: 128, micro_batch_size: 1 },
        optimizer: { ...FORM_DEFAULTS.automodel.optimizer, learning_rate: 5e-6 },
      },
    }),
  },
];
