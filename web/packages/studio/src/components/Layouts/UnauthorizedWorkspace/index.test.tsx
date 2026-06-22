// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { UnauthorizedWorkspace } from '@studio/components/Layouts/UnauthorizedWorkspace';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

const renderComponent = () =>
  render(
    <TestProviders>
      <MemoryRouter>
        <UnauthorizedWorkspace />
      </MemoryRouter>
    </TestProviders>
  );

describe('UnauthorizedWorkspace', () => {
  it('renders the access denied heading', () => {
    renderComponent();
    expect(screen.getByText("You don't have access to this workspace")).toBeInTheDocument();
  });

  it('renders the permission message', () => {
    renderComponent();
    expect(
      screen.getByText(
        "You don't have permission to view this workspace. Contact the workspace owner to request access."
      )
    ).toBeInTheDocument();
  });
});
