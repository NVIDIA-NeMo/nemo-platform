// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { server } from '@studio/mocks/node';
import { EvaluationTraceDetailRoute } from '@studio/routes/EvaluationTraceDetailRoute';
import { getEvaluationTraceDetailRoute } from '@studio/routes/utils';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

const WORKSPACE = 'default';
const EXPERIMENT_GROUP = 'my-group';
const EVALUATION_NAME = 'my-evaluation';
const COMPARE_EVALUATION_NAME = 'my-other-evaluation';
const GROUP_ID = 'group-uuid-001';
// Reuses the pre-wired mock traces from @studio/mocks/intake/telemetry
const TRACE_ID = 'trace-agent-run-001';
const COMPARE_TRACE_ID = 'trace-agent-run-002';
const TEST_CASE_ID = 'case-0042'; // matches the mock trace's experiment_context.test_case_id
const PRIMARY_SESSION_ID = 'sess-primary-AAAAA';
const COMPARE_SESSION_ID = 'sess-compare-BBBBB';

const PRIMARY_LABEL = `${EVALUATION_NAME} · Trial AAAAA`;
const COMPARE_LABEL = `${COMPARE_EVALUATION_NAME} · Trial BBBBB`;

const EXPERIMENT_GROUP_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/experiment-groups/${EXPERIMENT_GROUP}`;
const EVALUATIONS_LIST_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations`;
const PRIMARY_SESSIONS_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations/${EVALUATION_NAME}/sessions`;
const COMPARE_SESSIONS_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations/${COMPARE_EVALUATION_NAME}/sessions`;

const mockGroup = {
  id: GROUP_ID,
  name: EXPERIMENT_GROUP,
  workspace: WORKSPACE,
  default_sort: '-created_at',
};

const mockEvaluation = (name: string) => ({
  id: `eval-${name}`,
  name,
  workspace: WORKSPACE,
  experiment_group_id: GROUP_ID,
  dataset_name: 'my-dataset',
});

const mockSession = (evaluationName: string, sessionId: string, traceId: string) => ({
  workspace: WORKSPACE,
  evaluation_name: evaluationName,
  session_id: sessionId,
  trace_id: traceId,
  root_span_id: `span-root-${traceId}`,
  started_at: '2026-01-01T00:00:00Z',
  status: 'success',
  test_case_id: TEST_CASE_ID,
  latency_ms: 1200,
  input_tokens: 500,
  output_tokens: 250,
  cached_tokens: 0,
  cost_total_usd: 0.0123,
  evaluator_scores: { correctness: 0.9 },
});

const sessionsPage = (rows: object[]) =>
  HttpResponse.json({ data: rows, pagination: { page: 1, total_results: rows.length } });

/** MSW handlers for the group + fan-out session lookups every render fires. */
function registerHandlers() {
  server.use(
    http.get(EXPERIMENT_GROUP_URL, () => HttpResponse.json(mockGroup)),
    http.get(EVALUATIONS_LIST_URL, () =>
      HttpResponse.json({
        data: [mockEvaluation(EVALUATION_NAME), mockEvaluation(COMPARE_EVALUATION_NAME)],
        pagination: { page: 1, total_results: 2 },
      })
    ),
    http.get(PRIMARY_SESSIONS_URL, () =>
      sessionsPage([mockSession(EVALUATION_NAME, PRIMARY_SESSION_ID, TRACE_ID)])
    ),
    http.get(COMPARE_SESSIONS_URL, () =>
      sessionsPage([mockSession(COMPARE_EVALUATION_NAME, COMPARE_SESSION_ID, COMPARE_TRACE_ID)])
    )
  );
}

const renderTraceDetail = (compareWithTraceId?: string) => {
  const base = getEvaluationTraceDetailRoute(
    WORKSPACE,
    EXPERIMENT_GROUP,
    EVALUATION_NAME,
    TRACE_ID
  );
  const path = compareWithTraceId
    ? `${base}?compareWith=${encodeURIComponent(compareWithTraceId)}`
    : base;

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
  beforeEach(() => {
    registerHandlers();
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
    it('labels each column with its run (evaluation name · Trial)', async () => {
      renderTraceDetail(COMPARE_TRACE_ID);

      // Column labels come from the slotHeader render prop, which fires once the
      // trace + runs load — wait for both together.
      await waitFor(() => {
        expect(screen.getAllByText(PRIMARY_LABEL).length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText(COMPARE_LABEL).length).toBeGreaterThanOrEqual(1);
      });
    });

    it('renders the page header with the test case id', async () => {
      renderTraceDetail(COMPARE_TRACE_ID);
      expect(
        await screen.findByText(`Test case comparison — Test case ${TEST_CASE_ID}`)
      ).toBeInTheDocument();
    });

    it('shows "test case not available" when the selected run has no matching session', async () => {
      server.use(http.get(COMPARE_SESSIONS_URL, () => sessionsPage([])));

      renderTraceDetail(COMPARE_TRACE_ID);

      expect(await screen.findByText('Test case not available')).toBeInTheDocument();
    });
  });

  describe('compare run selector', () => {
    // Radix menus need these pointer/layout APIs that jsdom does not implement.
    beforeAll(() => {
      Element.prototype.hasPointerCapture = vi.fn();
      Element.prototype.scrollIntoView = vi.fn();
    });

    it('groups runs by evaluation and selecting one enters the comparison', async () => {
      const user = userEvent.setup();
      renderTraceDetail();

      // The trigger enables once the group's runs finish loading.
      const trigger = await screen.findByRole('combobox', {
        name: 'Compare against evaluation run',
      });
      await waitFor(() => expect(trigger).toBeEnabled());
      await user.click(trigger);

      // Panel title + the sibling evaluation as a group heading + its trial row.
      // The primary run (TRACE_ID) is excluded, so only the compare evaluation shows.
      expect(
        await screen.findByText('Select a trial from a run to compare against')
      ).toBeInTheDocument();
      expect(screen.getByText(COMPARE_EVALUATION_NAME)).toBeInTheDocument();

      await user.click(screen.getByRole('option', { name: /Trial BBBBB/ }));

      // Selecting the run swaps into the comparison view.
      expect(
        await screen.findByText(`Test case comparison — Test case ${TEST_CASE_ID}`)
      ).toBeInTheDocument();
    });
  });
});
