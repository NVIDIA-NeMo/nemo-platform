// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useOptimizerSuggestions } from '@studio/routes/agents/AgentSuggestionsRoute/useOptimizerSuggestions';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import { type FC, type PropsWithChildren } from 'react';

// Comparison path is gated by this flag — force it on for this file only.
vi.mock('@studio/constants/featureFlags', () => ({
  featureFlags: { optimizerComparisonEnabled: true },
}));

const mocks = vi.hoisted(() => ({
  applySuggestion: vi.fn(),
  ensureEvalConfigFileset: vi.fn(),
  fetchEvalAverageScores: vi.fn(),
  fetchProfilerStats: vi.fn(),
  loadSuggestionsFromFileset: vi.fn(),
  loadPreviousSuggestionsFromFileset: vi.fn(),
  markSuggestionAppliedInFileset: vi.fn(),
  submitEvalJob: vi.fn(),
  waitForDeployments: vi.fn(),
  waitForEvalJob: vi.fn(),
}));

vi.mock('@studio/routes/agents/AgentSuggestionsRoute/api', () => ({
  applySuggestion: (...a: unknown[]) => mocks.applySuggestion(...a),
  archivePreviousRun: vi.fn(),
  CONTENT_SAFETY_MODEL_RE: /content-safety/i,
  checkContentSafety: vi.fn(),
  ensureEvalConfigFileset: (...a: unknown[]) => mocks.ensureEvalConfigFileset(...a),
  fetchAgents: vi.fn(),
  fetchEvalAverageScores: (...a: unknown[]) => mocks.fetchEvalAverageScores(...a),
  fetchModels: vi.fn(),
  fetchPiiSample: vi.fn(),
  fetchProfilerStats: (...a: unknown[]) => mocks.fetchProfilerStats(...a),
  isCanceledError: () => false,
  loadPreviousSuggestionsFromFileset: (...a: unknown[]) =>
    mocks.loadPreviousSuggestionsFromFileset(...a),
  loadSnapshot: vi.fn(),
  loadSuggestionsFromFileset: (...a: unknown[]) => mocks.loadSuggestionsFromFileset(...a),
  markSuggestionAppliedInFileset: (...a: unknown[]) => mocks.markSuggestionAppliedInFileset(...a),
  SNAPSHOT_PATH: 'optimizer_snapshot.json',
  submitEvalJob: (...a: unknown[]) => mocks.submitEvalJob(...a),
  SUGGESTIONS_PATH: 'optimizer_suggestions.jsonl',
  uploadToFileset: vi.fn(),
  waitForDeployments: (...a: unknown[]) => mocks.waitForDeployments(...a),
  waitForEvalJob: (...a: unknown[]) => mocks.waitForEvalJob(...a),
}));

const createWrapper = (): FC<PropsWithChildren> => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

const suggestion = {
  type: 'model_optimization',
  title: 't',
  detail: 'd',
  agent: 'phish',
  model: 'big-120b',
  apply: [
    {
      method: 'POST' as const,
      path: '/apis/agents/v2/workspaces/ws-a/agents',
      body: { name: 'phish-nano' },
    },
    {
      method: 'POST' as const,
      path: '/apis/agents/v2/workspaces/ws-a/deployments',
      body: { agent: 'phish-nano' },
    },
    {
      method: 'POST' as const,
      path: '/apis/agents/v2/workspaces/ws-a/jobs/evaluate',
      body: {
        spec: {
          agent: 'phish-nano',
          eval_config: 'email-phishing-eval.yml',
          eval_config_fileset: 'phish-eval',
          output: 'phish-nano-eval-out',
        },
      },
    },
  ],
};

beforeEach(() => {
  mocks.applySuggestion
    .mockReset()
    .mockResolvedValue({ deploymentNames: ['deploy-1'], evalJobNames: ['eval-after'] });
  mocks.ensureEvalConfigFileset.mockReset().mockResolvedValue(undefined);
  mocks.fetchEvalAverageScores
    .mockReset()
    .mockResolvedValue([{ evaluator: 'recall', averageScore: 0.9 }]);
  mocks.fetchProfilerStats.mockReset().mockResolvedValue({
    avgTotalTokens: 800,
    avgPromptTokens: 600,
    avgCompletionTokens: 200,
    llmLatencyP95Seconds: 1.2,
    workflowRuntimeP95Seconds: 2.0,
  });
  mocks.loadSuggestionsFromFileset.mockReset().mockResolvedValue([]);
  mocks.loadPreviousSuggestionsFromFileset.mockReset().mockResolvedValue([]);
  mocks.markSuggestionAppliedInFileset.mockReset().mockResolvedValue(undefined);
  mocks.submitEvalJob.mockReset().mockResolvedValue('eval-before');
  mocks.waitForDeployments.mockReset().mockResolvedValue(undefined);
  mocks.waitForEvalJob.mockReset().mockResolvedValue(undefined);
});

describe('useOptimizerSuggestions comparison path', () => {
  it('re-scores the original agent and records a baseline run alongside the optimized one', async () => {
    const { result } = renderHook(() => useOptimizerSuggestions('ws-a'), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.apply(suggestion);
    });

    // Baseline eval submitted against the *original* agent with the same config.
    expect(mocks.submitEvalJob).toHaveBeenCalledWith(
      'ws-a',
      expect.objectContaining({
        agent: 'phish',
        eval_config: 'email-phishing-eval.yml',
        eval_config_fileset: 'phish-eval',
        output: 'phish-eval-out',
      }),
      expect.anything()
    );
    // Both runs' outputs were read (optimized + baseline output filesets).
    expect(mocks.fetchProfilerStats).toHaveBeenCalledWith(
      'ws-a',
      'phish-nano-eval-out',
      expect.anything()
    );
    expect(mocks.fetchProfilerStats).toHaveBeenCalledWith(
      'ws-a',
      'phish-eval-out',
      expect.anything()
    );

    const evalState = result.current.getEvalState(suggestion);
    expect(evalState?.status).toBe('completed');
    expect(evalState?.profiler?.avgTotalTokens).toBe(800);
    expect(evalState?.baseline).toEqual(
      expect.objectContaining({
        agentName: 'phish',
        jobName: 'eval-before',
        status: 'completed',
        scores: [{ evaluator: 'recall', averageScore: 0.9 }],
      })
    );
  });
});
