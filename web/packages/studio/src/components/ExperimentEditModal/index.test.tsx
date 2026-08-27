// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ExperimentResponse } from '@nemo/sdk/generated/platform/schema';
import { ExperimentEditModal } from '@studio/components/ExperimentEditModal';
import { server } from '@studio/mocks/node';
import { render, screen } from '@studio/tests/util/render';
import { waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

const WORKSPACE = 'test-workspace';

const group: ExperimentResponse = {
  id: 'group-id',
  name: 'opt-group',
  workspace: WORKSPACE,
  description: 'Editable group description',
  summary: 'Optimizer-authored summary',
  insight_id: 'insight-id',
  metadata: { producer: 'optimizer' },
  default_sort: '-created_at',
  evaluation_count: 0,
};

const TREND_KEY = `nemo-studio:experiment-trend:${group.id}`;

describe('ExperimentEditModal', () => {
  it('resends the fields it does not edit, which a full-replace update would otherwise clear', async () => {
    let body: Record<string, unknown> | undefined;
    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/evaluations', () =>
        HttpResponse.json({
          data: [],
          pagination: {
            page: 1,
            page_size: 100,
            current_page_size: 0,
            total_pages: 0,
            total_results: 0,
          },
        })
      ),
      http.put('*/apis/intake/v2/workspaces/:workspace/experiments/:name', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(group);
      })
    );

    render(<ExperimentEditModal open onClose={vi.fn()} workspace={WORKSPACE} group={group} />);

    await userEvent.click(await screen.findByRole('button', { name: 'Save' }));

    await waitFor(() => expect(body).toBeDefined());
    expect(body).toMatchObject({
      name: group.name,
      description: group.description,
      default_sort: group.default_sort,
      insight_id: group.insight_id,
      summary: group.summary,
      metadata: group.metadata,
    });
  });

  describe('over-time flag and the chart visibility a viewer stored', () => {
    const mockRequests = () => {
      let saved = false;
      server.use(
        http.get('*/apis/intake/v2/workspaces/:workspace/evaluations', () =>
          HttpResponse.json({
            data: [],
            pagination: {
              page: 1,
              page_size: 100,
              current_page_size: 0,
              total_pages: 0,
              total_results: 0,
            },
          })
        ),
        http.put('*/apis/intake/v2/workspaces/:workspace/experiments/:name', () => {
          saved = true;
          return HttpResponse.json(group);
        })
      );
      return () => saved;
    };

    beforeEach(() => {
      window.localStorage.clear();
    });

    it('drops the stored choice when the flag is flipped, so the new flag decides', async () => {
      const isSaved = mockRequests();
      // A viewer who had hidden the chart on an unflagged experiment.
      window.localStorage.setItem(TREND_KEY, 'false');

      render(<ExperimentEditModal open onClose={vi.fn()} workspace={WORKSPACE} group={group} />);
      await userEvent.click(await screen.findByRole('switch', { name: /evaluate over time/i }));
      await userEvent.click(screen.getByRole('button', { name: 'Save' }));

      await waitFor(() => expect(isSaved()).toBe(true));
      await waitFor(() => expect(window.localStorage.getItem(TREND_KEY)).toBeNull());
    });

    it('keeps the stored choice when the flag is left alone', async () => {
      const isSaved = mockRequests();
      window.localStorage.setItem(TREND_KEY, 'false');

      render(<ExperimentEditModal open onClose={vi.fn()} workspace={WORKSPACE} group={group} />);
      // Edit something else entirely; the viewer's chart choice is not this save's business.
      await userEvent.click(await screen.findByRole('switch', { name: /favorite/i }));
      await userEvent.click(screen.getByRole('button', { name: 'Save' }));

      await waitFor(() => expect(isSaved()).toBe(true));
      expect(window.localStorage.getItem(TREND_KEY)).toBe('false');
    });
  });
});
