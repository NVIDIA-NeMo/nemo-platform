// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  buildMetricRunChatPromptTemplate,
  buildMetricRunOnlineJobParams,
  getMetricPromptTemplateTextForValidation,
  getMetricRunValidationPromptTemplate,
  getModelSelectionFromSearchParam,
  getPromptTemplateTextForValidation,
} from '@studio/components/sidePanels/MetricRunSidePanel/utils';

describe('getModelSelectionFromSearchParam', () => {
  it('returns null when no model param is provided', () => {
    expect(getModelSelectionFromSearchParam(null, 'workspace-a')).toBeNull();
    expect(getModelSelectionFromSearchParam('', 'workspace-a')).toBeNull();
  });

  it('preserves fully-qualified model refs', () => {
    expect(getModelSelectionFromSearchParam('workspace-a/model-a', 'workspace-b')).toEqual({
      model: 'workspace-a/model-a',
    });
  });

  it('qualifies bare model names with the current workspace', () => {
    expect(getModelSelectionFromSearchParam('model-a', 'workspace-a')).toEqual({
      model: 'workspace-a/model-a',
    });
  });

  it('preserves adapter selections from deep links', () => {
    expect(getModelSelectionFromSearchParam('model-a::adapter-a', 'workspace-a')).toEqual({
      model: 'workspace-a/model-a',
      adapter: 'adapter-a',
    });
  });
});

describe('getPromptTemplateTextForValidation', () => {
  it('joins message content for file-field validation', () => {
    expect(
      getPromptTemplateTextForValidation([
        { role: 'system', content: 'Use {{context}}.', expanded: true },
        { role: 'user', content: 'Answer {{input}}', expanded: true },
      ])
    ).toBe('Use {{context}}.\nAnswer {{input}}');
  });
});

describe('getMetricPromptTemplateTextForValidation', () => {
  it('returns string metric prompt templates unchanged', () => {
    expect(getMetricPromptTemplateTextForValidation('Judge {{item.output}}')).toBe(
      'Judge {{item.output}}'
    );
  });

  it('extracts content from structured metric message templates', () => {
    expect(
      getMetricPromptTemplateTextForValidation({
        messages: [
          { role: 'system', content: 'Use {{item.context}}' },
          { role: 'user', content: 'Score {{sample.output_text}} against {{item.reference}}' },
        ],
      })
    ).toBe('Use {{item.context}}\nScore {{sample.output_text}} against {{item.reference}}');
  });

  it('combines metric and run prompt templates for validation', () => {
    expect(
      getMetricRunValidationPromptTemplate({
        metricPromptTemplate: {
          messages: [{ role: 'user', content: 'Metric uses {{item.rubric}}' }],
        },
        promptMessages: [{ role: 'user', content: 'Run uses {{input}}', expanded: true }],
      })
    ).toBe('Metric uses {{item.rubric}}\nRun uses {{input}}');
  });
});

describe('buildMetricRunChatPromptTemplate', () => {
  it('returns a messages prompt template with blank messages removed', () => {
    expect(
      buildMetricRunChatPromptTemplate([
        { role: 'system', content: ' Keep answers short. ', expanded: true },
        { role: 'user', content: '', expanded: true },
        { role: 'user', content: 'Question: {{input}}', expanded: false },
      ])
    ).toEqual({
      messages: [
        { role: 'system', content: ' Keep answers short. ' },
        { role: 'user', content: 'Question: {{input}}' },
      ],
    });
  });

  it('returns null when no message has content', () => {
    expect(
      buildMetricRunChatPromptTemplate([{ role: 'user', content: '  ', expanded: true }])
    ).toBeNull();
  });
});

describe('buildMetricRunOnlineJobParams', () => {
  it('returns undefined when no execution parameters are set', () => {
    expect(
      buildMetricRunOnlineJobParams({ inferenceParams: {}, ignore_request_failure: false })
    ).toBeUndefined();
  });

  it('includes inference params when provided', () => {
    expect(
      buildMetricRunOnlineJobParams({
        inferenceParams: { max_tokens: 512 },
        ignore_request_failure: false,
      })
    ).toEqual({ inference: { max_tokens: 512 } });
  });

  it('includes ignore_request_failure when enabled', () => {
    expect(
      buildMetricRunOnlineJobParams({ inferenceParams: {}, ignore_request_failure: true })
    ).toEqual({ ignore_request_failure: true });
  });

  it('merges inference params and ignore_request_failure', () => {
    expect(
      buildMetricRunOnlineJobParams({
        inferenceParams: { max_tokens: 256, temperature: 0 },
        ignore_request_failure: true,
      })
    ).toEqual({
      inference: { max_tokens: 256, temperature: 0 },
      ignore_request_failure: true,
    });
  });
});
