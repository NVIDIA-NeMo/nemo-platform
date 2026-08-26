// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import { SubmitEvaluationModal } from '@studio/components/evaluation/SubmitEvaluationModal';
import { server } from '@studio/mocks/node';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

const emptyPage = { data: [], pagination: { total: 0, page: 1, page_size: 100 } };

describe('SubmitEvaluationModal', () => {
  it('scopes the "Create from existing evaluation" list to the current agent', async () => {
    const evaluationsUrls: URL[] = [];
    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/evaluations', ({ request }) => {
        evaluationsUrls.push(new URL(request.url));
        return HttpResponse.json(emptyPage);
      })
    );

    const user = userEvent.setup();
    renderRoute(undefined, {
      history: `/workspaces/${DEFAULT_WORKSPACE}`,
      routes: [
        {
          path: '/workspaces/:workspace',
          element: (
            <SubmitEvaluationModal
              open
              onClose={() => {}}
              workspace={DEFAULT_WORKSPACE}
              agent="my-agent"
            />
          ),
        },
      ],
    });

    // The list query only fires in experiment mode; switch to it.
    await user.click(await screen.findByRole('radio', { name: 'Create from existing evaluation' }));

    await waitFor(() => {
      const filtered = evaluationsUrls.find((u) => u.searchParams.has('filter[agent_name]'));
      expect(filtered).toBeDefined();
      expect(filtered!.searchParams.get('filter[agent_name]')).toBe('my-agent');
    });
  });
});
