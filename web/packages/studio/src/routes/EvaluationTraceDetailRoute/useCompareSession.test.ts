// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { server } from '@studio/mocks/node';
import { useCompareSession } from '@studio/routes/EvaluationTraceDetailRoute/useCompareSession';
import { renderHook, waitFor } from '@studio/tests/util/render';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { http, HttpResponse } from 'msw';

const WORKSPACE = 'default';
const COMPARE_EVAL = 'evaluation-b';
const TEST_CASE_ID = 'case-0042';
const COMPARE_TRACE_ID = 'trace-compare-001';

const SESSIONS_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations/${COMPARE_EVAL}/sessions`;

const mockSession = {
  workspace: WORKSPACE,
  evaluation_name: COMPARE_EVAL,
  session_id: 'session-compare-001',
  trace_id: COMPARE_TRACE_ID,
  root_span_id: 'span-root-compare',
  started_at: '2026-01-01T00:00:00Z',
  status: 'success',
  test_case_id: TEST_CASE_ID,
};

const wrapper = TestProviders;

describe('useCompareSession', () => {
  it('returns status "found" when the compare evaluation has a matching session', async () => {
    server.use(
      http.get(SESSIONS_URL, () =>
        HttpResponse.json({ data: [mockSession], pagination: { page: 1, total_results: 1 } })
      )
    );

    const { result } = renderHook(
      () =>
        useCompareSession({
          workspace: WORKSPACE,
          compareEvaluationName: COMPARE_EVAL,
          testCaseId: TEST_CASE_ID,
        }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.status).toBe('found'));
    expect(result.current.status === 'found' && result.current.session.trace_id).toBe(
      COMPARE_TRACE_ID
    );
  });

  it('returns status "not-found" when no session matches the test_case_id', async () => {
    server.use(
      http.get(SESSIONS_URL, () =>
        HttpResponse.json({ data: [], pagination: { page: 1, total_results: 0 } })
      )
    );

    const { result } = renderHook(
      () =>
        useCompareSession({
          workspace: WORKSPACE,
          compareEvaluationName: COMPARE_EVAL,
          testCaseId: TEST_CASE_ID,
        }),
      { wrapper }
    );

    await waitFor(() => expect(result.current.status).toBe('not-found'));
    expect(result.current.status === 'not-found' && result.current.testCaseId).toBe(TEST_CASE_ID);
  });

  it('returns status "no-test-case-id" immediately when testCaseId is null', async () => {
    const { result } = renderHook(
      () =>
        useCompareSession({
          workspace: WORKSPACE,
          compareEvaluationName: COMPARE_EVAL,
          testCaseId: null,
        }),
      { wrapper }
    );

    // Synchronous — no query is started, no loading state
    expect(result.current.status).toBe('no-test-case-id');
  });

  it('returns status "no-test-case-id" when testCaseId is undefined', async () => {
    const { result } = renderHook(
      () =>
        useCompareSession({
          workspace: WORKSPACE,
          compareEvaluationName: COMPARE_EVAL,
          testCaseId: undefined,
        }),
      { wrapper }
    );

    expect(result.current.status).toBe('no-test-case-id');
  });

  it('returns status "loading" (not "no-test-case-id") when testCaseId is absent but still loading', () => {
    const { result } = renderHook(
      () =>
        useCompareSession({
          workspace: WORKSPACE,
          compareEvaluationName: COMPARE_EVAL,
          testCaseId: null,
          isTestCaseIdLoading: true,
        }),
      { wrapper }
    );

    expect(result.current.status).toBe('loading');
  });
});
