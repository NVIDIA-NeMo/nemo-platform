// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  fetchAgentEvalJob,
  fetchAgentEvalJobs,
  fetchAgentEvalOutputFiles,
  outputFilesetForJob,
  type AgentEvalJob,
} from '@studio/routes/agents/AgentEvaluationsRoute/api';

const customFetchMock = vi.fn();
vi.mock('@nemo/sdk/generated/fetchers/platform', () => ({
  customFetch: (...args: unknown[]) => customFetchMock(...args),
}));

const filesListFilesetFilesMock = vi.fn();
const filesDownloadFileMock = vi.fn();
vi.mock('@nemo/sdk/generated/platform/api', () => ({
  filesListFilesetFiles: (...args: unknown[]) => filesListFilesetFilesMock(...args),
  filesDownloadFile: (...args: unknown[]) => filesDownloadFileMock(...args),
}));

beforeEach(() => {
  customFetchMock.mockReset();
  filesListFilesetFilesMock.mockReset();
  filesDownloadFileMock.mockReset();
});

const baseJob = (overrides: Partial<AgentEvalJob> = {}): AgentEvalJob => ({
  name: 'eval-1',
  workspace: 'ws-a',
  status: 'completed',
  created_at: '2026-05-05T00:00:00Z',
  updated_at: '2026-05-05T00:01:00Z',
  spec: { agent: 'support-bot-mini', eval_config: 'eval.yaml' },
  ...overrides,
});

describe('fetchAgentEvalJobs', () => {
  it('paginates until a short page is returned', async () => {
    // Two full pages of 50 + a 1-item tail page; the helper must walk all
    // three to return the full list.
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

  it('returns an empty array when the first page is empty', async () => {
    customFetchMock.mockResolvedValueOnce({ data: [] });
    const all = await fetchAgentEvalJobs('ws-a', new AbortController().signal);
    expect(all).toEqual([]);
    expect(customFetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('fetchAgentEvalJob', () => {
  it('returns the job when the platform responds with one', async () => {
    customFetchMock.mockResolvedValueOnce(baseJob({ name: 'eval-42' }));
    const job = await fetchAgentEvalJob('ws-a', 'eval-42', new AbortController().signal);
    expect(job?.name).toBe('eval-42');
  });

  it('returns null when the platform returns no body', async () => {
    customFetchMock.mockResolvedValueOnce(undefined);
    const job = await fetchAgentEvalJob('ws-a', 'missing', new AbortController().signal);
    expect(job).toBeNull();
  });
});

describe('fetchAgentEvalOutputFiles', () => {
  it('treats 404 as an empty fileset (job ran but never wrote outputs)', async () => {
    filesListFilesetFilesMock.mockRejectedValueOnce({ response: { status: 404 } });
    const files = await fetchAgentEvalOutputFiles(
      'ws-a',
      'support-bot-mini-eval-out',
      new AbortController().signal
    );
    expect(files).toEqual([]);
  });

  it('rethrows non-404 errors so the caller can surface them', async () => {
    filesListFilesetFilesMock.mockRejectedValueOnce({ response: { status: 500 } });
    await expect(
      fetchAgentEvalOutputFiles('ws-a', 'fileset', new AbortController().signal)
    ).rejects.toMatchObject({ response: { status: 500 } });
  });
});

describe('outputFilesetForJob', () => {
  it('prefers spec.output verbatim when set as a bare name', () => {
    expect(outputFilesetForJob(baseJob({ spec: { output: 'custom-out' } }))).toBe('custom-out');
  });

  it('strips the workspace prefix from spec.output when given as workspace/name', () => {
    expect(outputFilesetForJob(baseJob({ spec: { output: 'ws-a/custom-out' } }))).toBe(
      'custom-out'
    );
  });

  it('falls back to <agent>-eval-out when spec.output is unset', () => {
    expect(outputFilesetForJob(baseJob({ spec: { agent: 'support-bot-mini' } }))).toBe(
      'support-bot-mini-eval-out'
    );
  });

  it('returns null when neither spec.output nor spec.agent is set', () => {
    expect(outputFilesetForJob(baseJob({ spec: {} }))).toBeNull();
  });
});
