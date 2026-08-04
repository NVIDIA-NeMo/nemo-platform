// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeTracesTable } from '@studio/components/IntakeLists/IntakeTracesTable';
import { mockTracesPage } from '@studio/mocks/intake/telemetry';
import { server } from '@studio/mocks/node';
import { renderRoute, screen, waitFor } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Route, Routes, useLocation } from 'react-router';

/**
 * React Router wraps location updates in React.startTransition, so the mount-time
 * started_at seed lands as a deferred render: the table paints its toolbar first and
 * only then adopts the filter and fetches. Every assertion here waits for that settled
 * state — a synchronous query right after the first paint races the transition and is
 * only reliable on machines fast enough to hide it.
 */
const SETTLE = { timeout: 10_000 };
const TEST_TIMEOUT = 30_000;

/** Resolves once the seeded filter has landed in the URL and been adopted by the table. */
const waitForSeededTable = () => screen.findByTestId('clear-filters', undefined, SETTLE);

const LocationProbe = () => {
  const location = useLocation();
  return (
    <output data-testid="trace-detail-location">{`${location.pathname}${location.search}`}</output>
  );
};

describe('IntakeTracesTable', () => {
  it(
    'loads trace rows in preview mode for bounded payloads and aggregate metrics',
    async () => {
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

      await waitForSeededTable();
      await screen.findByText('Answer customer policy question', undefined, SETTLE);
      await screen.findByText('Can I deploy this model in a private workspace?', undefined, SETTLE);
      await screen.findByText(
        'Yes. Use a private workspace and restrict access through workspace membership.',
        undefined,
        SETTLE
      );

      await waitFor(() => expect(requestedModes).toContain('preview'), SETTLE);
      expect(requestedModes).not.toContain('detailed');
      expect(requestedModes).not.toContain('summary');
    },
    TEST_TIMEOUT
  );

  it(
    'opens trace rows in the canonical session detail route',
    async () => {
      const user = userEvent.setup();

      renderRoute(
        <Routes>
          <Route
            path="/workspaces/:workspace/intake/traces"
            element={<IntakeTracesTable workspace="default" />}
          />
          <Route
            path="/workspaces/:workspace/intake/sessions/:sessionId"
            element={<LocationProbe />}
          />
        </Routes>,
        { history: '/workspaces/default/intake/traces' }
      );

      await waitForSeededTable();
      await user.click(
        await screen.findByText('Answer customer policy question', undefined, SETTLE)
      );

      await waitFor(
        () =>
          expect(screen.getByTestId('trace-detail-location')).toHaveTextContent(
            '/workspaces/default/intake/sessions/session-agent-run-001?traceId=trace-agent-run-001'
          ),
        SETTLE
      );
    },
    TEST_TIMEOUT
  );

  it(
    'seeds a clearable 30-day started_at filter into trace list requests',
    async () => {
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

      const clearFilters = await waitForSeededTable();
      await screen.findByText('Answer customer policy question', undefined, SETTLE);
      await waitFor(
        () => expect(startedAtParams.filter(Boolean).length).toBeGreaterThan(0),
        SETTLE
      );

      const seededGte = new Date(startedAtParams.filter(Boolean).at(-1) as string);
      const daysAgo = (Date.now() - seededGte.getTime()) / 86_400_000;
      expect(daysAgo).toBeGreaterThanOrEqual(29);
      expect(daysAgo).toBeLessThanOrEqual(31);

      await user.click(clearFilters);
      await waitFor(() => expect(startedAtParams.at(-1)).toBeNull(), SETTLE);
    },
    TEST_TIMEOUT
  );

  it(
    'shows explicit trace filter facets',
    async () => {
      const user = userEvent.setup();

      renderRoute(<IntakeTracesTable workspace="default" />, {
        history: '/workspaces/default/intake/traces',
      });

      await waitForSeededTable();
      await screen.findByText('Answer customer policy question', undefined, SETTLE);
      await user.click(await screen.findByTestId('open-filters-button', undefined, SETTLE));

      await screen.findByText('Trace ID', undefined, SETTLE);
      expect(screen.getByText('Started At')).toBeInTheDocument();
      expect(screen.queryByText('Status')).not.toBeInTheDocument();
      expect(screen.queryByText('Session ID')).not.toBeInTheDocument();
      expect(screen.queryByText('Evaluation Run ID')).not.toBeInTheDocument();
    },
    TEST_TIMEOUT
  );
});
