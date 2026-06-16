// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  extractPromptTemplateFields,
  validateMetricRunFileContent,
} from '@studio/components/sidePanels/MetricRunSidePanel/FileValidationPanel/utils';

describe('extractPromptTemplateFields', () => {
  it('extracts jinja and format-style template fields', () => {
    expect(
      extractPromptTemplateFields('Question: {{ item.input | trim }} Answer: {reference}')
    ).toEqual(['input', 'reference']);
  });

  it('returns root fields for nested item paths', () => {
    expect(
      extractPromptTemplateFields('{{item.messages[0].content}} {{ item.context.text }}')
    ).toEqual(['messages', 'context']);
  });

  it('ignores sample fields that are provided by evaluator outputs instead of the dataset', () => {
    expect(
      extractPromptTemplateFields('{{sample.output_text}} {{ item.reference }} {sample.score}')
    ).toEqual(['reference']);
  });
});

describe('validateMetricRunFileContent', () => {
  it('validates JSONL content and confirms prompt template fields', async () => {
    const result = await validateMetricRunFileContent({
      content: '{"prompt":"hello","completion":"hi"}\n{"prompt":"bye","completion":"goodbye"}',
      path: 'data.jsonl',
      promptTemplate: '{{item.prompt}}',
      jobType: 'online',
    });

    expect(result.isValid).toBe(true);
    expect(result.format).toBe('jsonl');
    expect(result.rowCount).toBe(2);
    expect(result.detectionResult?.schemaType).toBe('completion');
    expect(result.missingTemplateFields).toEqual([]);
  });

  it('reports prompt template fields missing from CSV content', async () => {
    const result = await validateMetricRunFileContent({
      content: 'prompt,completion\nhello,hi',
      path: 'data.csv',
      promptTemplate: '{{item.prompt}} {{item.context}}',
      jobType: 'online',
    });

    expect(result.isValid).toBe(true);
    expect(result.format).toBe('csv');
    expect(result.rootKeys).toEqual(['prompt', 'completion']);
    expect(result.missingTemplateFields).toEqual(['context']);
  });

  it('validates normalized parquet content without routing through JSONL file validation', async () => {
    const result = await validateMetricRunFileContent({
      content: '{"prompt":"hello","completion":"hi"}\n{"prompt":"bye","completion":"goodbye"}',
      path: 'data.parquet',
      promptTemplate: '{{item.prompt}}',
      jobType: 'online',
    });

    expect(result.isValid).toBe(true);
    expect(result.format).toBe('parquet');
    expect(result.rowCount).toBe(2);
    expect(result.detectionResult?.schemaType).toBe('completion');
    expect(result.missingTemplateFields).toEqual([]);
  });

  it('returns an invalid result for malformed normalized parquet content', async () => {
    const result = await validateMetricRunFileContent({
      content: 'not-json',
      path: 'data.parquet',
      promptTemplate: '',
      jobType: 'offline',
    });

    expect(result.isValid).toBe(false);
    expect(result.error).toBe('Parquet file preview could not be parsed');
  });

  it('returns an invalid result for malformed JSON', async () => {
    const result = await validateMetricRunFileContent({
      content: 'not-json',
      path: 'data.json',
      promptTemplate: '',
      jobType: 'offline',
    });

    expect(result.isValid).toBe(false);
    expect(result.error).toBeTruthy();
  });
});
