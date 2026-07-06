// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  aggregateCsvTokens,
  fetchProfilerStats,
  parseCsv,
} from '@studio/routes/agents/AgentSuggestionsRoute/api';

const filesListFilesetFilesMock = vi.fn();
const filesDownloadFileMock = vi.fn();

vi.mock('@nemo/sdk/generated/fetchers/platform', () => ({
  customFetch: vi.fn(),
}));

vi.mock('@nemo/sdk/generated/platform/api', () => ({
  filesCreateFileset: vi.fn(),
  filesDownloadFile: (...args: unknown[]) => filesDownloadFileMock(...args),
  filesListFilesetFiles: (...args: unknown[]) => filesListFilesetFilesMock(...args),
  filesUploadFile: vi.fn(),
  modelsListModels: vi.fn(),
}));

const mockBlob = (text: string): Blob => ({ text: () => Promise.resolve(text) }) as unknown as Blob;

const signal = new AbortController().signal;

beforeEach(() => {
  filesListFilesetFilesMock.mockReset();
  filesDownloadFileMock.mockReset();
});

describe('parseCsv', () => {
  it('parses a simple grid', () => {
    expect(parseCsv('a,b,c\n1,2,3')).toEqual([
      ['a', 'b', 'c'],
      ['1', '2', '3'],
    ]);
  });

  it('handles quoted fields with embedded commas and escaped quotes', () => {
    expect(parseCsv('name,note\n"Doe, Jane","say ""hi"""')).toEqual([
      ['name', 'note'],
      ['Doe, Jane', 'say "hi"'],
    ]);
  });

  it('treats \\r\\n as a single row break', () => {
    expect(parseCsv('a,b\r\n1,2\r\n')).toEqual([
      ['a', 'b'],
      ['1', '2'],
    ]);
  });
});

describe('aggregateCsvTokens', () => {
  it('averages token columns over distinct example_number', () => {
    // Two items (0, 1); two LLM calls for item 0. total_tokens sum = 100+50+80 = 230.
    const csv = [
      'example_number,event_type,prompt_tokens,completion_tokens,total_tokens',
      '0,LLM_END,60,40,100',
      '0,LLM_END,30,20,50',
      '1,LLM_END,50,30,80',
    ].join('\n');
    const agg = aggregateCsvTokens(csv);
    expect(agg.avgTotalTokens).toBeCloseTo(230 / 2);
    expect(agg.avgPromptTokens).toBeCloseTo(140 / 2);
    expect(agg.avgCompletionTokens).toBeCloseTo(90 / 2);
  });

  it('returns nulls when the token columns are absent', () => {
    expect(aggregateCsvTokens('example_number,event_type\n0,LLM_START')).toEqual({
      avgTotalTokens: null,
      avgPromptTokens: null,
      avgCompletionTokens: null,
    });
  });

  it('returns nulls for an empty / header-only file', () => {
    expect(aggregateCsvTokens('')).toEqual({
      avgTotalTokens: null,
      avgPromptTokens: null,
      avgCompletionTokens: null,
    });
  });
});

describe('fetchProfilerStats', () => {
  it('returns null when neither profiler artifact is present', async () => {
    filesListFilesetFilesMock.mockResolvedValueOnce({
      data: [{ path: 'eval/agent/recall_output.json' }],
    });
    await expect(fetchProfilerStats('ws', 'out', signal)).resolves.toBeNull();
    expect(filesDownloadFileMock).not.toHaveBeenCalled();
  });

  it('parses latency from inference_optimization.json and tokens from the CSV (nested paths)', async () => {
    filesListFilesetFilesMock.mockResolvedValueOnce({
      data: [
        { path: 'eval/email-phishing/inference_optimization.json' },
        { path: 'eval/email-phishing/standardized_data_all.csv' },
      ],
    });
    filesDownloadFileMock.mockImplementation((_ws, _fs, path: string) => {
      if (path.endsWith('inference_optimization.json')) {
        return Promise.resolve(
          mockBlob(
            JSON.stringify({
              confidence_intervals: {
                llm_latency_confidence_intervals: { mean: 1.1, p95: 2.5 },
                workflow_run_time_confidence_intervals: { mean: 3.0, p95: 4.2 },
              },
            })
          )
        );
      }
      return Promise.resolve(
        mockBlob('example_number,total_tokens,prompt_tokens,completion_tokens\n0,100,60,40')
      );
    });

    const stats = await fetchProfilerStats('ws', 'out', signal);
    expect(stats).not.toBeNull();
    expect(stats?.llmLatencyP95Seconds).toBe(2.5);
    expect(stats?.workflowRuntimeP95Seconds).toBe(4.2);
    expect(stats?.avgTotalTokens).toBe(100);
    expect(stats?.avgPromptTokens).toBe(60);
    expect(stats?.avgCompletionTokens).toBe(40);
  });

  it('falls back to CI mean when p95 is absent', async () => {
    filesListFilesetFilesMock.mockResolvedValueOnce({
      data: [{ path: 'inference_optimization.json' }],
    });
    filesDownloadFileMock.mockResolvedValueOnce(
      mockBlob(
        JSON.stringify({
          confidence_intervals: { llm_latency_confidence_intervals: { mean: 0.9 } },
        })
      )
    );
    const stats = await fetchProfilerStats('ws', 'out', signal);
    expect(stats?.llmLatencyP95Seconds).toBe(0.9);
    expect(stats?.workflowRuntimeP95Seconds).toBeNull();
    expect(stats?.avgTotalTokens).toBeNull();
  });

  it('returns null (not throw) when the listing fails with a non-cancel error', async () => {
    filesListFilesetFilesMock.mockRejectedValueOnce({ response: { status: 404 } });
    await expect(fetchProfilerStats('ws', 'out', signal)).resolves.toBeNull();
  });
});
