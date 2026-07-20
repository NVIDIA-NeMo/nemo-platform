// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeTracesTable } from '@studio/components/IntakeLists/IntakeTracesTable';
import { mockTracesPage } from '@studio/mocks/intake/telemetry';
import { server } from '@studio/mocks/node';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';

describe('IntakeTracesTable', () => {
  it('loads trace rows in preview mode for bounded payloads and aggregate metrics', async () => {
    const requestedModes: Array<string | null> = [];
    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/traces', ({ request }) => {
        requestedModes.push(new URL(request.url).searchParams.get('mode'));
        return HttpResponse.json(mockTracesPage);
      })
    );

    renderRoute(<IntakeTracesTable workspace="default" />, {
      history: '/workspaces/default/intake/traces',
    });

    await screen.findByText('Answer customer policy question');
    expect(screen.getByText('Can I deploy this model in a private workspace?')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Yes. Use a private workspace and restrict access through workspace membership.'
      )
    ).toBeInTheDocument();

    await waitFor(() => expect(requestedModes).toContain('preview'));
    expect(requestedModes).not.toContain('detailed');
    expect(requestedModes).not.toContain('summary');
  });

  it('seeds a clearable 30-day started_at filter into trace list requests', async () => {
    const user = userEvent.setup();
    const startedAtParams: Array<string | null> = [];
    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/traces', ({ request }) => {
        startedAtParams.push(new URL(request.url).searchParams.get('filter[started_at][$gte]'));
        return HttpResponse.json(mockTracesPage);
      })
    );

    renderRoute(<IntakeTracesTable workspace="default" />, {
      history: '/workspaces/default/intake/traces',
    });

    await screen.findByText('Answer customer policy question');
    await waitFor(() => expect(startedAtParams.filter(Boolean).length).toBeGreaterThan(0));

    const seededGte = new Date(startedAtParams.filter(Boolean).at(-1) as string);
    const daysAgo = (Date.now() - seededGte.getTime()) / 86_400_000;
    expect(daysAgo).toBeGreaterThanOrEqual(29);
    expect(daysAgo).toBeLessThanOrEqual(31);

    await user.click(screen.getByTestId('clear-filters'));
    await waitFor(() => expect(startedAtParams.at(-1)).toBeNull());
  });

  it('shows explicit trace filter facets', async () => {
    const user = userEvent.setup();

    renderRoute(<IntakeTracesTable workspace="default" />, {
      history: '/workspaces/default/intake/traces',
    });

    await screen.findByText('Answer customer policy question');
    await user.click(await screen.findByTestId('open-filters-button'));

    expect(screen.getByText('Trace ID')).toBeInTheDocument();
    expect(screen.getByText('Started At')).toBeInTheDocument();
    expect(screen.queryByText('Status')).not.toBeInTheDocument();
    expect(screen.queryByText('Session ID')).not.toBeInTheDocument();
    expect(screen.queryByText('Evaluation Run ID')).not.toBeInTheDocument();
  });
});
