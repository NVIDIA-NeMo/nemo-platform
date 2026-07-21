// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import type { InsightListItem } from '@studio/api/optimizer';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { server } from '@studio/mocks/node';
import { OptimizerRoute } from '@studio/routes/optimizer/OptimizerRoute';
import { getOptimizerRoute } from '@studio/routes/utils';
import { renderRoute, screen, within } from '@studio/tests/util/render';
import { http, HttpResponse } from 'msw';

const INSIGHTS_URL = `${PLATFORM_BASE_URL}/apis/insights/v2/workspaces/:workspace/insights`;
const EXPERIMENT_GROUPS_URL = '*/apis/intake/v2/workspaces/:workspace/experiment-groups';

const makeInsight = (id: string, title: string): InsightListItem => ({
  id,
  name: id,
  title,
  description: `${title} description`,
  agent: 'research-agent',
  status: 'open',
  trace_refs: ['trace-1'],
  experiment_group_count: null,
  created_at: '2026-07-20T12:00:00Z',
  updated_at: '2026-07-20T12:00:00Z',
});

const insightsPage = (data: InsightListItem[]) => ({
  data,
  pagination: {
    page: 1,
    page_size: 50,
    current_page_size: data.length,
    total_pages: 1,
    total_results: data.length,
  },
});

const renderList = () =>
  renderRoute(undefined, {
    history: getOptimizerRoute(DEFAULT_WORKSPACE),
    routes: [{ path: ROUTES.workspace.optimizer, element: <OptimizerRoute /> }],
  });

const findExperimentsCell = async (insightTitle: string): Promise<HTMLElement> => {
  const row = await screen.findByRole('row', { name: new RegExp(insightTitle) });

  const headers = screen.getAllByRole('columnheader');
  const experimentColumn = headers.findIndex((header) =>
    header.textContent?.includes('Experiments')
  );
  if (experimentColumn < 0) throw new Error('Experiments column not found');

  return within(row).getAllByRole('cell')[experimentColumn];
};

describe('OptimizerRoute', () => {
  it('renders server-provided experiment counts without requesting experiment groups', async () => {
    const experimentGroupRequest = vi.fn(() => HttpResponse.json({}));
    const insights = [
      { ...makeInsight('positive', 'Positive count'), experiment_group_count: 7 },
      { ...makeInsight('zero', 'Zero count'), experiment_group_count: 0 },
      makeInsight('null', 'Null count'),
    ];
    server.use(
      http.get(INSIGHTS_URL, () => HttpResponse.json(insightsPage(insights))),
      http.get(EXPERIMENT_GROUPS_URL, experimentGroupRequest)
    );

    renderList();

    expect(await findExperimentsCell('Positive count')).toHaveTextContent('7');
    expect(await findExperimentsCell('Zero count')).toHaveTextContent('0');
    expect(await findExperimentsCell('Null count')).toHaveTextContent('—');
    expect(experimentGroupRequest).not.toHaveBeenCalled();
  });
});
