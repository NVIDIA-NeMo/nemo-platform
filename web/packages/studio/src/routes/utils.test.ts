// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  getEvaluationBenchmarkDetailsRoute,
  getEvaluationBenchmarkListRoute,
  getEvaluationMetricDetailsRoute,
  getEvaluationMetricRunRoute,
  getEvaluationMetricsRunRoute,
  getPromptTuningFormRoute,
  getWorkspaceBaseModelsRoute,
  getWorkspaceInferenceProvidersRoute,
} from '@studio/routes/utils';

describe('Evaluation route helpers', () => {
  const workspace = 'test-namespace/test-project';

  describe('getEvaluationMetricDetailsRoute', () => {
    it('should generate correct evaluation metric details URL', () => {
      const jobId = 'job-123';

      const result = getEvaluationMetricDetailsRoute(workspace, jobId);

      expect(result).toBe('/workspaces/test-namespace/test-project/evaluation/metrics/job-123');
    });
  });

  describe('getEvaluationMetricsRunRoute', () => {
    it('appends an encoded model query param when a model is provided', () => {
      expect(getEvaluationMetricsRunRoute(workspace, { model: 'test-namespace/model-a' })).toBe(
        '/workspaces/test-namespace/test-project/evaluation/metrics/run?model=test-namespace%2Fmodel-a'
      );
    });
  });

  describe('getEvaluationMetricRunRoute', () => {
    it('appends an encoded model query param when a metric and model are provided', () => {
      expect(
        getEvaluationMetricRunRoute(workspace, 'toxicity', {
          model: 'test-namespace/model-a',
        })
      ).toBe(
        '/workspaces/test-namespace/test-project/evaluation/metrics/toxicity/run?model=test-namespace%2Fmodel-a'
      );
    });
  });

  describe('getEvaluationBenchmarkListRoute', () => {
    it('should generate the benchmarks list URL', () => {
      expect(getEvaluationBenchmarkListRoute(workspace)).toBe(
        '/workspaces/test-namespace/test-project/evaluation/benchmarks'
      );
    });
  });

  describe('getEvaluationBenchmarkDetailsRoute', () => {
    it('should generate a benchmark details URL', () => {
      expect(getEvaluationBenchmarkDetailsRoute(workspace, 'my-benchmark')).toBe(
        '/workspaces/test-namespace/test-project/evaluation/benchmarks/my-benchmark'
      );
    });
  });
});

describe('getWorkspaceInferenceProvidersRoute', () => {
  const workspace = 'test-namespace/test-project';

  it('returns base inference providers path when no options are given', () => {
    expect(getWorkspaceInferenceProvidersRoute(workspace)).toBe(
      '/workspaces/test-namespace/test-project/inference-providers'
    );
  });

  it('appends create=true and preset query params when a preset is provided', () => {
    expect(getWorkspaceInferenceProvidersRoute(workspace, { preset: 'build' })).toBe(
      '/workspaces/test-namespace/test-project/inference-providers?create=true&preset=build'
    );
  });
});

describe('getWorkspaceBaseModelsRoute (deep linking)', () => {
  const workspace = 'my-workspace';

  it('returns base models list path when no options', () => {
    expect(getWorkspaceBaseModelsRoute(workspace)).toBe('/workspaces/my-workspace/base-models');
  });

  it('encodes model names with special characters (e.g. slash) for the path', () => {
    expect(getWorkspaceBaseModelsRoute(workspace, { model: 'org/my-model' })).toBe(
      '/workspaces/my-workspace/base-models/org%2Fmy-model'
    );
  });

  it('appends tab query param when both model and tab are provided', () => {
    expect(
      getWorkspaceBaseModelsRoute(workspace, {
        model: 'my-model',
        tab: 'chat-playground',
      })
    ).toBe('/workspaces/my-workspace/base-models/my-model?tab=chat-playground');
  });

  it('preserves provided query params on model detail paths', () => {
    const searchParams = new URLSearchParams({
      s: 'llama',
      filters: JSON.stringify([{ id: 'customizable', value: { fine_tunable: true } }]),
      sort: '-created_at',
    });

    expect(getWorkspaceBaseModelsRoute(workspace, { model: 'my-model', searchParams })).toBe(
      `/workspaces/my-workspace/base-models/my-model?${searchParams.toString()}`
    );
  });

  it('combines provided query params with tab query param', () => {
    const searchParams = new URLSearchParams({ s: 'llama' });

    expect(
      getWorkspaceBaseModelsRoute(workspace, {
        model: 'my-model',
        tab: 'chat-playground',
        searchParams,
      })
    ).toBe('/workspaces/my-workspace/base-models/my-model?s=llama&tab=chat-playground');
  });

  it('preserves provided query params on base models list paths', () => {
    const searchParams = new URLSearchParams({ s: 'llama', sort: '-created_at' });

    expect(getWorkspaceBaseModelsRoute(workspace, { searchParams })).toBe(
      '/workspaces/my-workspace/base-models?s=llama&sort=-created_at'
    );
  });
});

describe('getPromptTuningFormRoute', () => {
  const workspace = 'my-workspace';

  it('returns the bare prompt tuning form path when no model is given', () => {
    expect(getPromptTuningFormRoute(workspace)).toBe(
      '/workspaces/my-workspace/customizations/prompt-tuned/new'
    );
  });

  it('appends an encoded ?model= query param when a model URN is provided', () => {
    expect(getPromptTuningFormRoute(workspace, { model: 'my-workspace/my-model' })).toBe(
      '/workspaces/my-workspace/customizations/prompt-tuned/new?model=my-workspace%2Fmy-model'
    );
  });
});
