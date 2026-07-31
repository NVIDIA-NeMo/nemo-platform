// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { CreateJobRequest as DataDesignerJobRequest } from '@nemo/sdk/generated/data-designer/schema';
import { ROUTES } from '@studio/constants/routes';
import { DataDesignerJobBuildRoute } from '@studio/routes/DataDesignerJobBuildRoute';
import type { DataDesignerGeneratedState } from '@studio/routes/DataDesignerJobBuildRoute/aiSeed';
import { getDataDesignerJobBuildRoute } from '@studio/routes/utils';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';

const BUILD_ROUTE = ROUTES.workspace.dataDesignerJobBuild;
const BUILD_PATH = getDataDesignerJobBuildRoute('default');

const generatedJobRequest: DataDesignerJobRequest = {
  name: 'phishing-emails',
  spec: {
    num_records: 400,
    config: {
      columns: [
        {
          name: 'topic',
          column_type: 'sampler',
          sampler_type: 'category',
          params: { values: ['invoice', 'password reset'] },
        },
        {
          name: 'email_body',
          column_type: 'llm-text',
          prompt: 'Write an email about {{ topic }}.',
          model_alias: 'gen',
        },
      ],
      model_configs: [{ alias: 'gen', model: 'default/llama-3.3', provider: 'default/nim' }],
    },
  },
} as unknown as DataDesignerJobRequest;

const renderBuildRoute = (state?: DataDesignerGeneratedState) => {
  const router = createMemoryRouter(
    [{ path: BUILD_ROUTE, element: <DataDesignerJobBuildRoute /> }],
    { initialEntries: [{ pathname: BUILD_PATH, state }] }
  );
  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe('DataDesignerJobBuildRoute', () => {
  it('loads a generated job request from router state into the builder', async () => {
    renderBuildRoute({ generatedJobRequest });

    expect(await screen.findByText('topic')).toBeInTheDocument();
    expect(await screen.findByText('email_body')).toBeInTheDocument();
  });

  it('opens empty when there is no seed in router state', async () => {
    renderBuildRoute();

    expect(await screen.findByText(/No columns yet/i)).toBeInTheDocument();
  });
});
