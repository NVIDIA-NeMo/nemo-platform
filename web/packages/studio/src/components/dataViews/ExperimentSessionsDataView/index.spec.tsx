// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ExperimentSessionsDataView } from '@studio/components/dataViews/ExperimentSessionsDataView';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { server } from '@studio/mocks/node';
import { getExperimentDetailRoute } from '@studio/routes/utils';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

vi.mock('use-debounce', () => ({
  useDebounce: (value: unknown) => [value, { cancel: () => {}, flush: () => {} }],
}));

const WORKSPACE = 'default';
const EXPERIMENT_GROUP = 'my-group';
const EXPERIMENT_NAME = 'my-experiment';
const TRACE_ID = 'trace-abc-123';

const SESSIONS_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/:workspace/experiments/:name/sessions`;
const EXPERIMENT_URL = `${PLATFORM_BASE_URL}/apis/intake/v2/workspaces/:workspace/experiments/:name`;

const mockSession = {
  workspace: WORKSPACE,
  experiment_name: EXPERIMENT_NAME,
  session_id: 'session-1',
  trace_id: TRACE_ID,
  root_span_id: 'span-root-1',
  started_at: '2025-01-01T00:00:00Z',
  status: 'success',
  test_case_id: 'case-1',
};

const mockSessionsPage = {
  data: [mockSession],
  pagination: { page: 1, page_size: 50, current_page_size: 1, total_pages: 1, total_results: 1 },
};

const mockExperiment = {
  workspace: WORKSPACE,
  name: EXPERIMENT_NAME,
  experiment_group_name: EXPERIMENT_GROUP,
  run_count: 1,
  evaluator_names: [],
};

const renderDataView = () =>
  renderRoute(undefined, {
    history: getExperimentDetailRoute(WORKSPACE, EXPERIMENT_GROUP, EXPERIMENT_NAME),
    routes: [
      {
        path: ROUTES.workspace.experimentDetail,
        element: (
          <ExperimentSessionsDataView
            experimentName={EXPERIMENT_NAME}
            experimentGroupName={EXPERIMENT_GROUP}
          />
        ),
      },
      {
        path: ROUTES.workspace.experimentTraceDetail,
        element: <div data-testid="trace-detail-route" />,
      },
    ],
  });

describe('ExperimentSessionsDataView', () => {
  beforeEach(() => {
    server.use(
      http.get(EXPERIMENT_URL, () => HttpResponse.json(mockExperiment)),
      http.get(SESSIONS_URL, () => HttpResponse.json(mockSessionsPage))
    );
  });

  afterEach(() => {
    server.resetHandlers();
  });

  it('renders a row for each session', async () => {
    renderDataView();
    // The Tooltip renders both a trigger and a hidden popover — getAllByText handles both.
    const matches = await screen.findAllByText('case-1');
    expect(matches.length).toBeGreaterThan(0);
  });

  it('navigates to the experiment trace route when a row is clicked', async () => {
    const user = userEvent.setup();
    renderDataView();

    // Click the tooltip trigger (first match); the row click handler delegates up from there.
    const [trigger] = await screen.findAllByText('case-1');
    await user.click(trigger);

    expect(await screen.findByTestId('trace-detail-route')).toBeInTheDocument();
  });

  it('does not navigate when the session has no trace_id', async () => {
    server.use(
      http.get(SESSIONS_URL, () =>
        HttpResponse.json({
          ...mockSessionsPage,
          data: [{ ...mockSession, trace_id: '', test_case_id: 'no-trace-case' }],
        })
      )
    );
    const user = userEvent.setup();
    renderDataView();

    const [trigger] = await screen.findAllByText('no-trace-case');
    await user.click(trigger);

    // Route should not have changed — trace-detail-route element is absent.
    expect(screen.queryByTestId('trace-detail-route')).not.toBeInTheDocument();
  });
});
