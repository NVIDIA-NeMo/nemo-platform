// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ExperimentResponse } from '@nemo/sdk/generated/platform/schema';
import { ROUTES } from '@studio/constants/routes';
import { server } from '@studio/mocks/node';
import { ExperimentDetailRoute } from '@studio/routes/ExperimentDetailRoute';
import { renderRoute, screen } from '@studio/tests/util/render';
import { http, HttpResponse } from 'msw';

vi.hoisted(() => {
  vi.stubEnv('VITE_FF_OPTIMIZER_ENABLED', 'false');
});

const WORKSPACE = 'test-workspace';
const GROUP_NAME = 'test-group';

const group = {
  id: 'group-id',
  name: GROUP_NAME,
  workspace: WORKSPACE,
  description: 'Editable group description',
  summary: 'Generated group summary',
  insight_id: 'insight-id',
  default_sort: '-created_at',
  evaluation_count: 0,
} satisfies Partial<ExperimentResponse>;

const mockGroup = (overrides?: Partial<ExperimentResponse>) => {
  const insightRequest = vi.fn();
  server.use(
    http.get('*/apis/intake/v2/workspaces/:workspace/experiments/:name', () =>
      HttpResponse.json({ ...group, ...overrides })
    ),
    http.get('*/apis/intake/v2/workspaces/:workspace/evaluations', () =>
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
    http.get('*/apis/insights/v2/workspaces/:workspace/insights/:insightId', () => {
      insightRequest();
      return HttpResponse.json({});
    })
  );

  renderRoute(<ExperimentDetailRoute />, {
    history: `/workspaces/${WORKSPACE}/experiment/${GROUP_NAME}`,
    routes: [
      {
        path: ROUTES.workspace.experimentDetail,
        element: <ExperimentDetailRoute />,
      },
    ],
  });

  return insightRequest;
};

describe('ExperimentDetailRoute', () => {
  it('renders the group description and summary without requesting Optimizer when disabled', async () => {
    const insightRequest = mockGroup();

    expect(await screen.findByText('Editable group description')).toBeInTheDocument();
    expect(screen.getByText('Generated group summary')).toBeInTheDocument();
    expect(insightRequest).not.toHaveBeenCalled();
    expect(screen.queryByRole('link', { name: /originating insight/i })).not.toBeInTheDocument();
  });

  it('omits the summary panel for groups no producer has summarized', async () => {
    mockGroup({ summary: undefined });

    expect(await screen.findByText('Editable group description')).toBeInTheDocument();
    expect(screen.queryByText('Summary')).not.toBeInTheDocument();
  });
});
