// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { server } from '@studio/mocks/node';
import { EvaluationTraceDetailRoute } from '@studio/routes/EvaluationTraceDetailRoute';
import { getEvaluationTraceDetailRoute } from '@studio/routes/utils';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import { http, HttpResponse } from 'msw';

const WORKSPACE = 'default';
const EXPERIMENT_GROUP = 'my-group';
const EVALUATION_NAME = 'my-evaluation';
const COMPARE_EVALUATION_NAME = 'my-other-evaluation';
const GROUP_ID = 'group-uuid-001';
const DATASET_NAME = 'my-dataset';
// Reuses the pre-wired mock trace from @studio/mocks/intake/telemetry
const TRACE_ID = 'trace-agent-run-001';
const COMPARE_TRACE_ID = 'trace-agent-run-002';
const TEST_CASE_ID = 'case-0042'; // matches the mock trace's experiment_context.test_case_id

const EXPERIMENT_GROUP_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/experiment-groups/${EXPERIMENT_GROUP}`;
const EVALUATION_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations/${EVALUATION_NAME}`;
const EVALUATIONS_LIST_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations`;
const COMPARE_SESSIONS_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations/${COMPARE_EVALUATION_NAME}/sessions`;
const COMPARE_EVALUATION_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations/${COMPARE_EVALUATION_NAME}`;
const PRIMARY_SESSIONS_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations/${EVALUATION_NAME}/sessions`;

const mockGroup = {
  id: GROUP_ID,
  name: EXPERIMENT_GROUP,
  workspace: WORKSPACE,
  default_sort: '-created_at',
};

const mockPrimaryEvaluation = {
  id: 'eval-uuid-001',
  name: EVALUATION_NAME,
  workspace: WORKSPACE,
  experiment_group_id: GROUP_ID,
  dataset_name: DATASET_NAME,
};

const mockCompareEvaluation = {
  id: 'eval-uuid-002',
  name: COMPARE_EVALUATION_NAME,
  workspace: WORKSPACE,
  experiment_group_id: GROUP_ID,
  dataset_name: DATASET_NAME,
};

const mockCompareSession = {
  workspace: WORKSPACE,
  evaluation_name: COMPARE_EVALUATION_NAME,
  session_id: 'session-compare-001',
  trace_id: COMPARE_TRACE_ID,
  root_span_id: 'span-root-compare',
  started_at: '2026-01-01T00:00:00Z',
  status: 'success',
  test_case_id: TEST_CASE_ID,
};

/** MSW handlers for the evaluation/group entity lookups the route fires. */
function registerEvaluationHandlers() {
  server.use(
    http.get(EXPERIMENT_GROUP_URL, () => HttpResponse.json(mockGroup)),
    http.get(EVALUATION_URL, () => HttpResponse.json(mockPrimaryEvaluation)),
    http.get(COMPARE_EVALUATION_URL, () => HttpResponse.json(mockCompareEvaluation)),
    http.get(EVALUATIONS_LIST_URL, () =>
      HttpResponse.json({
        data: [mockPrimaryEvaluation, mockCompareEvaluation],
        pagination: { page: 1, total_results: 2 },
      })
    ),
    http.get(PRIMARY_SESSIONS_URL, () =>
      HttpResponse.json({ data: [], pagination: { page: 1, total_results: 0 } })
    )
  );
}

const renderTraceDetail = (compareWith?: string) => {
  const base = getEvaluationTraceDetailRoute(
    WORKSPACE,
    EXPERIMENT_GROUP,
    EVALUATION_NAME,
    TRACE_ID
  );
  const path = compareWith ? `${base}?compareWith=${encodeURIComponent(compareWith)}` : base;

  return renderRoute(undefined, {
    history: path,
    routes: [
      {
        path: '/workspaces/:workspace/experiment/:experimentGroupName/:evaluationName/traces/:traceId',
        element: <EvaluationTraceDetailRoute />,
      },
    ],
  });
};

describe('EvaluationTraceDetailRoute', () => {
  // Every render fires the evaluation/group fetches that populate the compare selector.
  beforeEach(() => {
    registerEvaluationHandlers();
  });

  describe('single trace view (no compareWith param)', () => {
    it('renders the trace detail content', async () => {
      renderTraceDetail();
      expect(await screen.findByText('Test case: case-0042')).toBeInTheDocument();
    });

    it('renders the evaluation context panel', async () => {
      renderTraceDetail();
      await screen.findByText('Test case: case-0042');
      expect(screen.getByText('Evaluation Context')).toBeInTheDocument();
    });

    it('does not render an Intake link in the page content', async () => {
      renderTraceDetail();
      await screen.findByText('Test case: case-0042');
      expect(screen.queryByRole('link', { name: 'Intake' })).not.toBeInTheDocument();
    });
  });

  describe('compare view (compareWith query param set)', () => {
    it('renders both column header labels with evaluation names', async () => {
      server.use(
        http.get(COMPARE_SESSIONS_URL, () =>
          HttpResponse.json({
            data: [mockCompareSession],
            pagination: { page: 1, total_results: 1 },
          })
        )
      );

      renderTraceDetail(COMPARE_EVALUATION_NAME);

      // Both names are rendered by the slotHeader render prop inside TraceSpanAccordions,
      // which only fires after the trace loads — wait for both together.
      await waitFor(() => {
        expect(screen.getAllByText(EVALUATION_NAME).length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText(COMPARE_EVALUATION_NAME).length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows "test case not available" when the compare evaluation has no matching session', async () => {
      server.use(
        http.get(COMPARE_SESSIONS_URL, () =>
          HttpResponse.json({ data: [], pagination: { page: 1, total_results: 0 } })
        )
      );

      renderTraceDetail(COMPARE_EVALUATION_NAME);

      expect(await screen.findByText('Test case not available')).toBeInTheDocument();
    });

    it('renders the primary evaluation column header', async () => {
      server.use(
        http.get(COMPARE_SESSIONS_URL, () =>
          HttpResponse.json({
            data: [mockCompareSession],
            pagination: { page: 1, total_results: 1 },
          })
        )
      );

      renderTraceDetail(COMPARE_EVALUATION_NAME);

      // Text kind="title/sm" is not a semantic heading — assert by text content.
      expect(await screen.findByText(EVALUATION_NAME)).toBeInTheDocument();
    });
  });
});
