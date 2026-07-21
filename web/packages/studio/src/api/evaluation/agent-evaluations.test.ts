// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentEvaluateJob } from '@nemo/sdk/generated/evaluator/schema';
import {
  type AgentEvalBundle,
  type AgentEvalResult,
  agentNameForJob,
  aggregateScoresOf,
  fetchAgentEvalJob,
  fetchAgentEvalJobs,
  joinBundleByTask,
  parseBundleRef,
} from '@studio/api/evaluation/agent-evaluations';

const customFetchMock = vi.fn();
vi.mock('@nemo/sdk/generated/fetchers/evaluator', () => ({
  customFetch: (...args: unknown[]) => customFetchMock(...args),
}));

const filesDownloadFileMock = vi.fn();
vi.mock('@nemo/sdk/generated/platform/api', () => ({
  filesDownloadFile: (...args: unknown[]) => filesDownloadFileMock(...args),
}));

beforeEach(() => {
  customFetchMock.mockReset();
  filesDownloadFileMock.mockReset();
});

const baseJob = (overrides: Partial<AgentEvaluateJob> = {}): AgentEvaluateJob =>
  ({
    name: 'eval-1',
    workspace: 'ws-a',
    status: 'completed',
    created_at: '2026-05-05T00:00:00Z',
    updated_at: '2026-05-05T00:01:00Z',
    spec: { target: { kind: 'agent', agent: { name: 'support-bot-mini' } }, tasks: [{}, {}] },
    ...overrides,
  }) as AgentEvaluateJob;

describe('fetchAgentEvalJobs', () => {
  it('walks all pages until a short page ends pagination', async () => {
    const page1 = Array.from({ length: 50 }, (_, i) => baseJob({ name: `j-${i}` }));
    const page2 = Array.from({ length: 50 }, (_, i) => baseJob({ name: `j-${50 + i}` }));
    const page3 = [baseJob({ name: 'j-100' })];
    customFetchMock
      .mockResolvedValueOnce({ data: page1 })
      .mockResolvedValueOnce({ data: page2 })
      .mockResolvedValueOnce({ data: page3 });
    const all = await fetchAgentEvalJobs('ws-a', new AbortController().signal);
    expect(all).toHaveLength(101);
    expect(customFetchMock).toHaveBeenCalledTimes(3);
  });

  it('targets the agent-evaluate endpoint', async () => {
    customFetchMock.mockResolvedValueOnce({ data: [] });
    await fetchAgentEvalJobs('ws-a', new AbortController().signal);
    expect(customFetchMock).toHaveBeenCalledWith(
      expect.objectContaining({
        url: '/apis/evaluator/v2/workspaces/ws-a/agent-evaluate/jobs',
      })
    );
  });
});

describe('fetchAgentEvalJob', () => {
  it('returns the job when the platform responds with one', async () => {
    customFetchMock.mockResolvedValueOnce(baseJob({ name: 'eval-42' }));
    const job = await fetchAgentEvalJob('ws-a', 'eval-42', new AbortController().signal);
    expect(job?.name).toBe('eval-42');
  });

  it('returns null on 404', async () => {
    customFetchMock.mockRejectedValueOnce({ response: { status: 404 } });
    const job = await fetchAgentEvalJob('ws-a', 'missing', new AbortController().signal);
    expect(job).toBeNull();
  });
});

describe('agentNameForJob', () => {
  it('reads the agent name from the target', () => {
    expect(agentNameForJob(baseJob())).toBe('support-bot-mini');
  });

  it('returns null when no target agent is set', () => {
    expect(agentNameForJob(baseJob({ spec: {} as AgentEvaluateJob['spec'] }))).toBeNull();
  });
});

describe('aggregateScoresOf', () => {
  it('flattens the nested scores shape', () => {
    const result = {
      scores: {
        scores: [{ name: 'llm-judge.accuracy', count: 5, nan_count: 0, score_type: 'range' }],
      },
    } as AgentEvalResult;
    expect(aggregateScoresOf(result)).toHaveLength(1);
    expect(aggregateScoresOf(null)).toEqual([]);
  });
});

describe('parseBundleRef', () => {
  it('splits "workspace/fileset#inner/path"', () => {
    expect(parseBundleRef('default/job-fileset-x#results/attempt-1/agent-eval-results')).toEqual({
      fileset: 'job-fileset-x',
      innerPath: 'results/attempt-1/agent-eval-results',
    });
  });

  it('returns null without a fragment', () => {
    expect(parseBundleRef('default/job-fileset-x')).toBeNull();
  });
});

describe('joinBundleByTask', () => {
  it('joins tasks, trials, and scores by task id', () => {
    const bundle: AgentEvalBundle = {
      tasks: [
        {
          id: 'A',
          intent: 'classify',
          inputs: { instruction: 'email a' },
          reference: { label: 'phishing' },
        },
      ],
      trials: [
        { id: 't1', task_id: 'A', status: 'completed', output: { output_text: 'phishing' } },
      ],
      scores: [
        {
          id: 's1',
          task_id: 'A',
          trial_id: 't1',
          metric_type: 'llm-judge',
          status: 'completed',
          outputs: [{ name: 'accuracy', value: 1 }],
          diagnostics: [],
        },
      ],
    };
    const [row] = joinBundleByTask(bundle);
    expect(row.taskId).toBe('A');
    expect(row.responseText).toBe('phishing');
    expect(row.instruction).toBe('email a');
    expect(row.reference).toEqual({ label: 'phishing' });
    expect(row.scores).toEqual([{ name: 'llm-judge.accuracy', value: 1 }]);
  });

  it('returns [] for a null bundle', () => {
    expect(joinBundleByTask(null)).toEqual([]);
  });

  it('normalizes serialized NaN score values for display', () => {
    const bundle: AgentEvalBundle = {
      tasks: [{ id: 'A' }],
      trials: [{ id: 't1', task_id: 'A', status: 'completed' }],
      scores: [
        {
          id: 's1',
          task_id: 'A',
          trial_id: 't1',
          metric_type: 'llm-judge',
          status: 'completed',
          outputs: [{ name: 'accuracy', value: 'NaN' }],
        },
      ],
    };

    expect(joinBundleByTask(bundle)[0].scores).toEqual([
      { name: 'llm-judge.accuracy', value: null },
    ]);
  });
});
