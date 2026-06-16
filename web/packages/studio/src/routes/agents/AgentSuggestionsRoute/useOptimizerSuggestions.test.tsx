// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useOptimizerSuggestions } from '@studio/routes/agents/AgentSuggestionsRoute/useOptimizerSuggestions';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { type FC, type PropsWithChildren } from 'react';

const mocks = vi.hoisted(() => ({
  applySuggestion: vi.fn(),
  archivePreviousRun: vi.fn(),
  checkContentSafety: vi.fn(),
  ensureEvalConfigFileset: vi.fn(),
  fetchAgents: vi.fn(),
  fetchEvalAverageScores: vi.fn(),
  fetchModels: vi.fn(),
  fetchPiiSample: vi.fn(),
  loadPreviousSuggestionsFromFileset: vi.fn(),
  loadSnapshot: vi.fn(),
  loadSuggestionsFromFileset: vi.fn(),
  markSuggestionAppliedInFileset: vi.fn(),
  uploadToFileset: vi.fn(),
  waitForDeployments: vi.fn(),
  waitForEvalJob: vi.fn(),
}));

vi.mock('@studio/routes/agents/AgentSuggestionsRoute/api', () => ({
  applySuggestion: (...args: unknown[]) => mocks.applySuggestion(...args),
  archivePreviousRun: (...args: unknown[]) => mocks.archivePreviousRun(...args),
  CONTENT_SAFETY_MODEL_RE: /content[.-]?safety|safety[.-]?guard|gliner/i,
  checkContentSafety: (...args: unknown[]) => mocks.checkContentSafety(...args),
  ensureEvalConfigFileset: (...args: unknown[]) => mocks.ensureEvalConfigFileset(...args),
  fetchAgents: (...args: unknown[]) => mocks.fetchAgents(...args),
  fetchEvalAverageScores: (...args: unknown[]) => mocks.fetchEvalAverageScores(...args),
  fetchModels: (...args: unknown[]) => mocks.fetchModels(...args),
  fetchPiiSample: (...args: unknown[]) => mocks.fetchPiiSample(...args),
  isCanceledError: (err: unknown): boolean => {
    const e = err as { name?: string; code?: string };
    return e?.name === 'AbortError' || e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED';
  },
  loadPreviousSuggestionsFromFileset: (...args: unknown[]) =>
    mocks.loadPreviousSuggestionsFromFileset(...args),
  loadSnapshot: (...args: unknown[]) => mocks.loadSnapshot(...args),
  loadSuggestionsFromFileset: (...args: unknown[]) => mocks.loadSuggestionsFromFileset(...args),
  markSuggestionAppliedInFileset: (...args: unknown[]) =>
    mocks.markSuggestionAppliedInFileset(...args),
  SNAPSHOT_PATH: 'optimizer_snapshot.json',
  SUGGESTIONS_PATH: 'optimizer_suggestions.jsonl',
  uploadToFileset: (...args: unknown[]) => mocks.uploadToFileset(...args),
  waitForDeployments: (...args: unknown[]) => mocks.waitForDeployments(...args),
  waitForEvalJob: (...args: unknown[]) => mocks.waitForEvalJob(...args),
}));

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T | PromiseLike<T>) => void;
  reject: (reason?: unknown) => void;
}

const deferred = <T,>(): Deferred<T> => {
  let resolve!: Deferred<T>['resolve'];
  let reject!: Deferred<T>['reject'];
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

const createWrapper = (): FC<PropsWithChildren> => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

beforeEach(() => {
  mocks.applySuggestion.mockReset().mockResolvedValue({ deploymentNames: [], evalJobNames: [] });
  mocks.archivePreviousRun.mockReset().mockResolvedValue(undefined);
  mocks.checkContentSafety.mockReset().mockResolvedValue(false);
  mocks.ensureEvalConfigFileset.mockReset().mockResolvedValue(undefined);
  mocks.fetchAgents.mockReset().mockResolvedValue([]);
  mocks.fetchEvalAverageScores.mockReset().mockResolvedValue([]);
  mocks.fetchModels.mockReset().mockResolvedValue([]);
  mocks.fetchPiiSample.mockReset().mockResolvedValue('');
  mocks.loadPreviousSuggestionsFromFileset.mockReset().mockResolvedValue([]);
  mocks.loadSnapshot.mockReset().mockResolvedValue(null);
  mocks.loadSuggestionsFromFileset.mockReset().mockResolvedValue([]);
  mocks.markSuggestionAppliedInFileset.mockReset().mockResolvedValue(undefined);
  mocks.uploadToFileset.mockReset().mockResolvedValue(undefined);
  mocks.waitForDeployments.mockReset().mockResolvedValue(undefined);
  mocks.waitForEvalJob.mockReset().mockResolvedValue(undefined);
});

describe('useOptimizerSuggestions run lifecycle', () => {
  it('aborts an active optimizer run on unmount', async () => {
    let runSignal: AbortSignal | undefined;
    mocks.fetchAgents.mockImplementation((_workspace: unknown, signal: AbortSignal) => {
      runSignal = signal;
      return new Promise((_resolve, reject) => {
        signal.addEventListener(
          'abort',
          () => reject(new DOMException('Run aborted', 'AbortError')),
          { once: true }
        );
      });
    });

    const { result, unmount } = renderHook(() => useOptimizerSuggestions('ws-a'), {
      wrapper: createWrapper(),
    });

    let runPromise: Promise<void> | undefined;
    act(() => {
      runPromise = result.current.run();
    });
    await waitFor(() => expect(result.current.phase).toBe('running'));

    unmount();

    if (!runPromise) throw new Error('run promise was not started');
    await runPromise;

    expect(runSignal?.aborted).toBe(true);
    expect(mocks.uploadToFileset).not.toHaveBeenCalled();
  });

  it('tracks eval state per suggestion: queued → running → completed with scores', async () => {
    const suggestion = {
      type: 'model_optimization',
      title: 't',
      detail: 'd',
      agent: 'support-bot',
      model: 'big',
      apply: [
        {
          method: 'POST' as const,
          path: '/apis/agents/v2/workspaces/ws-a/agents',
          body: { name: 'support-bot-mini' },
        },
        {
          method: 'POST' as const,
          path: '/apis/agents/v2/workspaces/ws-a/deployments',
          body: { agent: 'support-bot-mini' },
        },
        {
          method: 'POST' as const,
          path: '/apis/agents/v2/workspaces/ws-a/jobs/evaluate',
          body: { spec: { agent: 'support-bot-mini', eval_config: 'eval.yml' } },
        },
      ],
    };
    mocks.applySuggestion.mockResolvedValue({
      deploymentNames: ['deploy-1'],
      evalJobNames: ['eval-1'],
    });
    // Simulate the platform job emitting "running" before resolving as completed.
    mocks.waitForEvalJob.mockImplementation(
      async (_ws: unknown, _name: unknown, opts: { onStatus?: (status: string) => void }) => {
        opts.onStatus?.('running');
      }
    );
    mocks.fetchEvalAverageScores.mockResolvedValue([{ evaluator: 'accuracy', averageScore: 0.72 }]);

    const { result } = renderHook(() => useOptimizerSuggestions('ws-a'), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.apply(suggestion);
    });

    // Eval-state seeded from the apply array's POST /jobs/evaluate step.
    expect(mocks.ensureEvalConfigFileset).toHaveBeenCalledWith(
      'ws-a',
      'support-bot-eval',
      expect.anything()
    );
    expect(mocks.waitForEvalJob).toHaveBeenCalledWith(
      'ws-a',
      'eval-1',
      expect.objectContaining({ signal: expect.anything() })
    );
    // The output fileset name follows the sibling-agent convention.
    expect(mocks.fetchEvalAverageScores).toHaveBeenCalledWith(
      'ws-a',
      'support-bot-mini-eval-out',
      expect.anything()
    );

    const evalState = result.current.getEvalState(suggestion);
    expect(evalState).toEqual(
      expect.objectContaining({
        jobName: 'eval-1',
        siblingAgentName: 'support-bot-mini',
        status: 'completed',
        scores: [{ evaluator: 'accuracy', averageScore: 0.72 }],
      })
    );
  });

  it('records eval failure status without rolling back the apply', async () => {
    const suggestion = {
      type: 'model_optimization',
      title: 't',
      detail: 'd',
      agent: 'support-bot',
      model: 'big',
      apply: [
        {
          method: 'POST' as const,
          path: '/apis/agents/v2/workspaces/ws-a/agents',
          body: { name: 'support-bot-mini' },
        },
        {
          method: 'POST' as const,
          path: '/apis/agents/v2/workspaces/ws-a/deployments',
          body: { agent: 'support-bot-mini' },
        },
        {
          method: 'POST' as const,
          path: '/apis/agents/v2/workspaces/ws-a/jobs/evaluate',
          body: { spec: { agent: 'support-bot-mini', eval_config: 'eval.yml' } },
        },
      ],
    };
    mocks.applySuggestion.mockResolvedValue({
      deploymentNames: ['deploy-1'],
      evalJobNames: ['eval-1'],
    });
    mocks.waitForEvalJob.mockRejectedValue(new Error('Evaluation failed: judge model 404'));

    const { result } = renderHook(() => useOptimizerSuggestions('ws-a'), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.apply(suggestion);
    });

    const evalState = result.current.getEvalState(suggestion);
    expect(evalState?.status).toBe('failed');
    expect(evalState?.error).toMatch(/judge model 404/);
    // Apply itself is still considered applied — the agent was created. The
    // tile shows a failed eval row alongside the green Applied state.
    expect(result.current.getApplyState(suggestion).error).toBeNull();
  });

  it('resets state and ignores stale run results after workspace changes', async () => {
    const agents = deferred<[]>();
    let runSignal: AbortSignal | undefined;
    mocks.fetchAgents.mockImplementation((_workspace: unknown, signal: AbortSignal) => {
      runSignal = signal;
      return agents.promise;
    });

    const { result, rerender } = renderHook(({ workspace }) => useOptimizerSuggestions(workspace), {
      initialProps: { workspace: 'ws-a' },
      wrapper: createWrapper(),
    });

    let runPromise: Promise<void> | undefined;
    act(() => {
      runPromise = result.current.run();
    });
    await waitFor(() => expect(result.current.phase).toBe('running'));

    rerender({ workspace: 'ws-b' });
    await waitFor(() => expect(result.current.phase).toBe('idle'));
    expect(runSignal?.aborted).toBe(true);

    await act(async () => {
      agents.resolve([]);
      if (!runPromise) throw new Error('run promise was not started');
      await runPromise;
    });

    expect(result.current.phase).toBe('idle');
    expect(mocks.uploadToFileset).not.toHaveBeenCalled();
  });
});
