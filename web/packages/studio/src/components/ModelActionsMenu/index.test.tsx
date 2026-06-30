// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelActionsMenu } from '@studio/components/ModelActionsMenu';
import { entityStoreBaseModel1 } from '@studio/mocks/entity-store/models';
import { mockUseNavigate } from '@studio/tests/util/mockUseParams';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('ModelActionsMenu', () => {
  beforeEach(() => {
    mockUseNavigate();
  });
  afterEach(() => {
    vi.resetAllMocks();
  });

  const openMenu = async () => {
    const user = userEvent.setup();
    const triggers = await screen.findAllByTestId('quick-actions-menu-trigger');
    expect(triggers).not.toHaveLength(0);
    await user.click(triggers[0]);
  };
  it('should render the menu with the correct actions', async () => {
    render(
      <ModelActionsMenu
        workspace="test-project"
        model={entityStoreBaseModel1}
        onClickOpen={vi.fn()}
        onClickDelete={vi.fn()}
      />
    );
    await openMenu();
    expect(await screen.findByRole('menuitem', { name: 'Open' })).not.toBeDisabled();
    expect(screen.getByRole('menuitem', { name: 'Clone and Edit' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Delete' })).toBeInTheDocument();
  });
});
