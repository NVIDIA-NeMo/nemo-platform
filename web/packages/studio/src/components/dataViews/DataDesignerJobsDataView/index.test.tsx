// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  PlatformJobResponse,
  PlatformJobResponsesPage,
  PlatformJobStatus,
} from '@nemo/sdk/generated/platform/schema';
import { DataDesignerJobsDataView } from '@studio/components/dataViews/DataDesignerJobsDataView';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { server } from '@studio/mocks/node';
import { getDataDesignerJobListRoute } from '@studio/routes/utils';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import { fireEvent } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

vi.mock('@studio/components/DataDesignerJobActionsMenu', () => ({
  DataDesignerJobActionsMenu: () => <div data-testid="create-job-actions" />,
}));

const JOBS_URL = `${PLATFORM_BASE_URL}/apis/jobs/v2/workspaces/:workspace/jobs`;
const WORKSPACE = workspace1.workspace;

const makeJob = (overrides: Partial<PlatformJobResponse> = {}): PlatformJobResponse => ({
  id: 'job-id-1',
  attempt_id: 'attempt-1',
  name: 'data-generation-job',
  workspace: WORKSPACE,
  source: 'nemo-data-designer-plugin',
  spec: {},
  fileset: 'job-artifacts',
  status: PlatformJobStatus.completed,
  platform_spec: { steps: [] },
  created_at: '2026-08-13T08:00:00Z',
  updated_at: '2026-08-13T08:05:00Z',
  ...overrides,
});

const makeJobsPage = (jobs: PlatformJobResponse[]): PlatformJobResponsesPage => ({
  data: jobs,
  pagination: {
    page: 1,
    page_size: 25,
    current_page_size: jobs.length,
    total_pages: 1,
    total_results: jobs.length,
  },
});

const renderComponent = () =>
  renderRoute(undefined, {
    history: getDataDesignerJobListRoute(WORKSPACE),
    routes: [
      {
        path: ROUTES.workspace.dataDesignerJobList,
        element: <DataDesignerJobsDataView />,
      },
      {
        path: ROUTES.workspace.jobDetail,
        element: <div>Generic job details</div>,
      },
    ],
  });

describe('DataDesignerJobsDataView', () => {
  it('lists both data generation and dataset build jobs', async () => {
    const jobs = [
      makeJob(),
      makeJob({
        id: 'job-id-2',
        name: 'tcca-atif-build',
        source: 'nemo-data-designer.build-dataset',
        spec: {
          destination: { name: 'tcca-atif-dataset' },
          source: { kind: 'intake-traces', agent_name: 'tcca', trace_ids: ['trace-1'] },
        },
      }),
    ];
    server.use(http.get(JOBS_URL, () => HttpResponse.json(makeJobsPage(jobs))));

    renderComponent();

    expect(await screen.findByText('data-generation-job')).toBeInTheDocument();
    expect(screen.getByText('tcca-atif-build')).toBeInTheDocument();
    expect(screen.getByText('Data generation')).toBeInTheDocument();
    expect(screen.getByText('Dataset build')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'tcca-atif-dataset' })).toBeInTheDocument();
  });

  it('filters the generic jobs API to Data Designer sources', async () => {
    const requestUrls: string[] = [];
    server.use(
      http.get(JOBS_URL, ({ request }) => {
        requestUrls.push(request.url);
        return HttpResponse.json(makeJobsPage([]));
      })
    );

    renderComponent();

    await waitFor(() => expect(requestUrls.length).toBeGreaterThan(0));
    const params = new URL(requestUrls.at(-1)!).searchParams;
    const sources = params.getAll('filter[source][$in]').join(',');
    expect(sources).toContain('nemo-data-designer-plugin');
    expect(sources).toContain('nemo-data-designer.build-dataset');
  });

  it('opens a dataset build in the generic job details route', async () => {
    server.use(
      http.get(JOBS_URL, () =>
        HttpResponse.json(
          makeJobsPage([
            makeJob({
              name: 'tcca-atif-build',
              source: 'nemo-data-designer.build-dataset',
              spec: { destination: { name: 'tcca-atif-dataset' } },
            }),
          ])
        )
      )
    );

    renderComponent();

    fireEvent.click(await screen.findByText('tcca-atif-build'));
    expect(await screen.findByText('Generic job details')).toBeInTheDocument();
  });
});
