// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CUSTOMIZATION_TEMPLATES } from '@studio/constants/customizationTemplates';
import { customizationFormSchema } from '@studio/util/forms/customization';

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
      // The student/base model always comes from the models list; a teacher model
      // (distillation) must also be registered so its fileset exists.
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
});
