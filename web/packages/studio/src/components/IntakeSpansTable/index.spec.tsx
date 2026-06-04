// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeSpansTable } from '@studio/components/IntakeSpansTable';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

describe('IntakeSpansTable', () => {
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
