// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeSpansTable } from '@studio/components/IntakeLists/IntakeSpansTable';
import { mockSpansPage } from '@studio/mocks/intake/telemetry';
import { server } from '@studio/mocks/node';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { useLocation } from 'react-router-dom';

const LocationProbe = () => {
  const location = useLocation();
  return (
    <output data-testid="trace-detail-location">{`${location.pathname}${location.search}`}</output>
  );
};

describe('IntakeSpansTable', () => {
  it('opens span rows in the trace detail route with the span deep link', async () => {
    const user = userEvent.setup();

    renderRoute(undefined, {
      history: '/workspaces/default/intake/spans',
      routes: [
        {
          path: '/workspaces/:workspace/intake/spans',
          element: <IntakeSpansTable workspace="default" />,
        },
        {
          path: '/workspaces/:workspace/intake/traces/:traceId',
          element: <LocationProbe />,
        },
      ],
    });

    await user.click(await screen.findByText('Answer customer policy question'));

    expect(await screen.findByTestId('trace-detail-location')).toHaveTextContent(
      '/workspaces/default/intake/traces/trace-agent-run-001?spanId=span-root-001'
    );
  });

  it('seeds a clearable 30-day started_at filter into span list requests', async () => {
    const user = userEvent.setup();
    const startedAtParams: Array<string | null> = [];
    server.use(
      http.get('*/apis/intake/v2/workspaces/:workspace/spans', ({ request }) => {
        startedAtParams.push(new URL(request.url).searchParams.get('filter[started_at][$gte]'));
        return HttpResponse.json(mockSpansPage);
      })
    );

    renderRoute(<IntakeSpansTable workspace="default" />, {
      history: '/workspaces/default/intake/spans',
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

  it('shows explicit span filter facets', async () => {
    const user = userEvent.setup();

    renderRoute(<IntakeSpansTable workspace="default" />, {
      history: '/workspaces/default/intake/spans',
    });

    await screen.findByText('Answer customer policy question');
    await user.click(await screen.findByTestId('open-filters-button'));

    expect(screen.getAllByText('Status').length).toBeGreaterThan(1);
    expect(screen.getAllByText('Kind').length).toBeGreaterThan(1);
    expect(screen.getByText('Trace ID')).toBeInTheDocument();
    expect(screen.getByText('Started At')).toBeInTheDocument();
    expect(screen.queryByText('Session ID')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText('Search by span ID')).not.toBeInTheDocument();
  });
});
