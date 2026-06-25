// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IntakeTracesTable } from '@studio/components/IntakeLists/IntakeTracesTable';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

describe('IntakeTracesTable', () => {
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
