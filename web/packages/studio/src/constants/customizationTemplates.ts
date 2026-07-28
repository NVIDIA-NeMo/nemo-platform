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

export const CUSTOMIZATION_TEMPLATES: CustomizationTemplate[] = [
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
