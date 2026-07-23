// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { server } from '@studio/mocks/node';
import { useTestCaseRuns } from '@studio/routes/EvaluationTraceDetailRoute/useTestCaseRuns';
import { renderHook, waitFor } from '@studio/tests/util/render';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { http, HttpResponse } from 'msw';

const WORKSPACE = 'default';
const TEST_CASE_ID = 'case-0042';

const sessionsUrl = (evaluation: string) =>
  `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations/${evaluation}/sessions`;

const mockSession = (evaluation: string, traceId: string) => ({
  workspace: WORKSPACE,
  evaluation_name: evaluation,
  session_id: `sess-${traceId}`,
  trace_id: traceId,
  root_span_id: `span-${traceId}`,
  started_at: '2026-01-01T00:00:00Z',
  status: 'success',
  test_case_id: TEST_CASE_ID,
});

const wrapper = TestProviders;

describe('useTestCaseRuns', () => {
  it('fans out across evaluations and flattens the runs', async () => {
    server.use(
      http.get(sessionsUrl('eval-a'), () =>
        HttpResponse.json({
          data: [mockSession('eval-a', 'trace-a')],
          pagination: { page: 1, total_results: 1 },
        })
      ),
      http.get(sessionsUrl('eval-b'), () =>
        HttpResponse.json({
          data: [mockSession('eval-b', 'trace-b')],
          pagination: { page: 1, total_results: 1 },
        })
      )
    );

    const { result } = renderHook(
      () =>
        useTestCaseRuns({
          workspace: WORKSPACE,
          evaluationNames: ['eval-a', 'eval-b'],
          testCaseId: TEST_CASE_ID,
        }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.runs).toHaveLength(2));
    expect(result.current.runs.map((r) => r.trace_id).sort()).toEqual(['trace-a', 'trace-b']);
    expect(result.current.isLoading).toBe(false);
  });

  it('is disabled (no runs, not loading) when there is no test case id', () => {
    const { result } = renderHook(
      () =>
        useTestCaseRuns({
          workspace: WORKSPACE,
          evaluationNames: ['eval-a', 'eval-b'],
          testCaseId: null,
        }),
      { wrapper }
    );

    expect(result.current.runs).toHaveLength(0);
    expect(result.current.isLoading).toBe(false);
  });

  it('is disabled when there are no evaluations to query', () => {
    const { result } = renderHook(
      () =>
        useTestCaseRuns({ workspace: WORKSPACE, evaluationNames: [], testCaseId: TEST_CASE_ID }),
      { wrapper }
    );

    expect(result.current.runs).toHaveLength(0);
    expect(result.current.isLoading).toBe(false);
  });
});
