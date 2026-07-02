// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeSpansTable } from '@studio/components/IntakeLists/IntakeSpansTable';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';
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
