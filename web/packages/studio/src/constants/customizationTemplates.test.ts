// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CUSTOMIZATION_TEMPLATES } from '@studio/constants/customizationTemplates';
import { customizationFormSchema, formToAutomodelCreate } from '@studio/util/forms/customization';

const WORKSPACE = 'my-workspace';
const DATASET_REF = 'my-workspace/sft-dataset';

describe('CUSTOMIZATION_TEMPLATES', () => {
  it('exposes unique template ids', () => {
    const ids = CUSTOMIZATION_TEMPLATES.map((t) => t.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  describe.each(CUSTOMIZATION_TEMPLATES.map((t) => [t.id, t] as const))('%s', (_id, template) => {
    const fields = template.buildFormSpec(WORKSPACE, DATASET_REF);

    it('builds form fields that pass the customization schema', () => {
      const result = customizationFormSchema.safeParse(fields);
      expect(result.success).toBe(true);
    });

    it('namespaces the base model with the workspace', () => {
      expect(fields.automodel.model.startsWith(`${WORKSPACE}/`)).toBe(true);
    });

    it('wires the created dataset into training and validation', () => {
      expect(fields.automodel.dataset.training).toBe(DATASET_REF);
      expect(fields.automodel.dataset.validation).toBe(DATASET_REF);
    });

    it('registers every model it references', () => {
      const registered = template.models.map((m) => `${WORKSPACE}/${m.name}`);
      expect(registered).toContain(fields.automodel.model);
      const teacher = fields.automodel.training.teacher_model;
      if (teacher) expect(registered).toContain(teacher);
    });
  });

  it('marks gated (Llama) templates as requiring an HF token and open ones as not', () => {
    const byId = Object.fromEntries(CUSTOMIZATION_TEMPLATES.map((t) => [t.id, t]));
    expect(byId['sft-llama'].models.every((m) => m.requiresHfToken)).toBe(true);
    expect(byId['lora-qwen3'].models.some((m) => m.requiresHfToken)).toBe(false);
  });

  describe('lora-nemotron-3-super-text2sql', () => {
    const template = CUSTOMIZATION_TEMPLATES.find(
      (t) => t.id === 'lora-nemotron-3-super-text2sql'
    )!;
    const fields = template.buildFormSpec(WORKSPACE, DATASET_REF);
    const { automodel } = fields;

    it('requires an HF token and trust_remote_code for the gated Nemotron checkpoint', () => {
      expect(template.models).toHaveLength(1);
      expect(template.models[0].hfRepoId).toBe('nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16');
      expect(template.models[0].requiresHfToken).toBe(true);
      expect(template.models[0].trustRemoteCode).toBe(true);
    });

    it('spreads the MoE experts across all 8 GPUs', () => {
      // The point of the recipe: without ep_size matching the GPU count, a 120B A12B
      // MoE will not fit on a single 8x80GB node.
      expect(automodel.parallelism?.expert_parallel_size).toBe(8);
      expect(automodel.parallelism?.num_gpus_per_node).toBe(8);
      expect(automodel.parallelism?.num_nodes).toBe(1);
      expect(automodel.parallelism?.tensor_parallel_size).toBe(1);
    });

    it('excludes out_proj from LoRA, where Nemotron mamba kernels bypass adapters', () => {
      expect(automodel.training.lora?.exclude_modules).toEqual(['*.out_proj']);
    });

    it('mirrors the cookbook LoRA and optimizer settings', () => {
      expect(automodel.training.lora?.rank).toBe(8);
      expect(automodel.training.lora?.alpha).toBe(32);
      expect(automodel.training.lora?.use_triton).toBe(true);
      expect(automodel.training.max_seq_length).toBe(4096);
      expect(automodel.training.precision).toBe('bf16');
      expect(automodel.optimizer?.learning_rate).toBe(1e-5);
      expect(automodel.optimizer?.weight_decay).toBe(0);
      expect(automodel.optimizer?.optimizer).toBe('Adam');
      expect(automodel.optimizer?.lr_decay_style).toBe('cosine');
      expect(automodel.batch?.global_batch_size).toBe(8);
      expect(automodel.batch?.micro_batch_size).toBe(1);
      expect(automodel.schedule?.epochs).toBe(1);
    });

    it('survives the round trip into a create-job request', () => {
      // exclude_modules and expert_parallel_size are optional passthrough fields; a
      // recipe that set them only to have the mapper drop them would silently OOM.
      const spec = formToAutomodelCreate(fields).spec;
      expect(spec.training.lora?.exclude_modules).toEqual(['*.out_proj']);
      expect(spec.parallelism?.expert_parallel_size).toBe(8);
    });
  });

  it('sets a teacher model only for the distillation template', () => {
    const distillation = CUSTOMIZATION_TEMPLATES.find((t) => t.id === 'distillation-llama');
    const fields = distillation!.buildFormSpec(WORKSPACE, DATASET_REF);
    expect(fields.automodel.training.training_type).toBe('distillation');
    expect(fields.automodel.training.teacher_model).toBe(`${WORKSPACE}/llama-3-2-3b-teacher`);
  });
});

describe('template dataset converters', () => {
  const squadDataset = CUSTOMIZATION_TEMPLATES.find((t) => t.id === 'lora-qwen3')!.dataset;
  const specterDataset = CUSTOMIZATION_TEMPLATES.find(
    (t) => t.id === 'embedding-nemotron'
  )!.dataset;

  it('converts a SQuAD row into prompt/completion', () => {
    const row = {
      context: 'The sky is blue.',
      question: 'What color?',
      answers: { text: ['blue'] },
    };
    expect(squadDataset.convertRow(row)).toEqual({
      prompt: 'Context: The sky is blue. Question: What color? Answer:',
      completion: 'blue',
    });
  });

  it('drops SQuAD rows without an answer', () => {
    expect(
      squadDataset.convertRow({ context: 'x', question: 'y', answers: { text: [] } })
    ).toBeNull();
  });

  it('converts a SPECTER triplet into query/pos_doc/neg_doc', () => {
    expect(specterDataset.convertRow({ set: ['q', 'pos', 'neg'] })).toEqual({
      query: 'q',
      pos_doc: 'pos',
      neg_doc: ['neg'],
    });
  });

  it('drops SPECTER rows missing a triplet member', () => {
    expect(specterDataset.convertRow({ set: ['q', 'pos'] })).toBeNull();
  });

  describe('BIRD-SQL converter', () => {
    const birdDataset = CUSTOMIZATION_TEMPLATES.find(
      (t) => t.id === 'lora-nemotron-3-super-text2sql'
    )!.dataset;

    it('lays out schema, question and evidence as the cookbook prompt', () => {
      expect(
        birdDataset.convertRow({
          schema: 'CREATE TABLE t (id INT);',
          question: 'How many rows?',
          evidence: 'rows refers to COUNT(*)',
          SQL: 'SELECT COUNT(*) FROM t',
        })
      ).toEqual({
        prompt: 'CREATE TABLE t (id INT);\n\nHow many rows?\nrows refers to COUNT(*)',
        completion: 'SELECT COUNT(*) FROM t',
      });
    });

    it('keeps rows with empty evidence, which is common upstream', () => {
      const converted = birdDataset.convertRow({
        schema: 'CREATE TABLE t (id INT);',
        question: 'How many rows?',
        evidence: '',
        SQL: 'SELECT COUNT(*) FROM t',
      });
      expect(converted).not.toBeNull();
      expect(converted?.prompt).toBe('CREATE TABLE t (id INT);\n\nHow many rows?\n');
    });

    it.each([
      ['schema', { question: 'q', SQL: 'SELECT 1' }],
      ['question', { schema: 's', SQL: 'SELECT 1' }],
      ['SQL', { schema: 's', question: 'q' }],
    ])('drops rows missing %s', (_field, row) => {
      expect(birdDataset.convertRow(row)).toBeNull();
    });
  });
});
