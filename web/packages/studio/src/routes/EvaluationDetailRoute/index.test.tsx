// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { EvaluationResponse, ExperimentResponse } from '@nemo/sdk/generated/platform/schema';
import { ROUTES } from '@studio/constants/routes';
import { server } from '@studio/mocks/node';
import { EvaluationDetailRoute } from '@studio/routes/EvaluationDetailRoute';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

vi.hoisted(() => {
  vi.stubEnv('VITE_FF_OPTIMIZER_ENABLED', 'true');
});

const WORKSPACE = 'test-workspace';
const GROUP_NAME = 'test-group';
const EVALUATION_NAME = 'test-evaluation';

const evaluation = {
  id: 'evaluation-id',
  name: EVALUATION_NAME,
  workspace: WORKSPACE,
  experiment_group_id: 'group-id',
  dataset_name: 'dataset',
  description: 'Evaluation description',
} satisfies Partial<EvaluationResponse>;

const group = {
  id: 'group-id',
  name: GROUP_NAME,
  workspace: WORKSPACE,
  insight_id: 'insight-id',
  default_sort: '-created_at',
  evaluation_count: 0,
} satisfies Partial<ExperimentResponse>;

const mockRoutes = (insightDescription: string) =>
  server.use(
    http.get('*/apis/intake/v2/workspaces/:workspace/evaluations/:name', () =>
      HttpResponse.json(evaluation)
    ),
    http.get('*/apis/intake/v2/workspaces/:workspace/experiments/:name', () =>
      HttpResponse.json(group)
    ),
    http.get('*/apis/intake/v2/workspaces/:workspace/evaluations/:name/sessions', () =>
      HttpResponse.json({
        data: [],
        pagination: {
          page: 1,
          page_size: 25,
          current_page_size: 0,
          total_pages: 0,
          total_results: 0,
        },
      })
    ),
    http.get('*/apis/insights/v2/workspaces/:workspace/insights/:insightId', () =>
      HttpResponse.json({
        id: 'insight-id',
        name: 'insight',
        title: 'Insight',
        description: insightDescription,
        agent: 'agent',
        status: 'open',
        trace_refs: [],
      })
    )
  );

const renderEvaluation = () =>
  renderRoute(<EvaluationDetailRoute />, {
    history: `/workspaces/${WORKSPACE}/experiment/${GROUP_NAME}/${EVALUATION_NAME}`,
    routes: [
      {
        path: ROUTES.workspace.evaluationDetail,
        element: <EvaluationDetailRoute />,
      },
    ],
  });

describe('EvaluationDetailRoute with Optimizer enabled', () => {
  it('renders the originating insight description instead of relabeling the evaluation description', async () => {
    mockRoutes('Actual insight description');

    renderEvaluation();

    expect(await screen.findByText('Actual insight description')).toBeInTheDocument();
    expect(screen.getByText('Insight description')).toBeInTheDocument();
    expect(screen.queryByText('Evaluation description')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /originating insight/i })).toHaveAttribute(
      'href',
      `/workspaces/${WORKSPACE}/optimizer/insight-id`
    );
  });

  it('truncates a long insight description until it is expanded', async () => {
    const description = `${'Observed behavior. '.repeat(40)}End of description.`;
    mockRoutes(description);

    renderEvaluation();

    const showMore = await screen.findByText('Show more');
    expect(screen.queryByText(description)).not.toBeInTheDocument();

    await userEvent.click(showMore);

    expect(screen.getByText(description)).toBeInTheDocument();
    expect(screen.getByText('Show less')).toBeInTheDocument();
  });
});
