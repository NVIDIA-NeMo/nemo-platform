// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getEntityReference } from '@nemo/common/src/namedEntity';
import { CustomizationFilesetDetailsPanel } from '@studio/components/CustomizationFilesetDetailsPanel';
import { dataset } from '@studio/mocks/datasets';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const filesetUri = getEntityReference(dataset);

describe('CustomizationFilesetDetailsPanel', () => {
  const user = userEvent.setup();

  const renderPanel = () =>
    render(
      <TestProviders>
        <CustomizationFilesetDetailsPanel filesetUri={filesetUri} />
      </TestProviders>
    );

  const awaitActiveViewButton = async () => {
    await waitFor(
      () => {
        const buttons = screen.getAllByRole('button', { name: 'View' });
        expect(buttons[0]).toBeEnabled();
      },
      { timeout: 5000 }
    );
    return screen.getAllByRole('button', { name: 'View' })[0];
  };

  it('should render a fileset details panel', async () => {
    renderPanel();

    const buttons = screen.getAllByRole('button', { name: 'View' });

    expect(screen.getByText(filesetUri)).toBeInTheDocument();
    // Expect to be disabled while loading files
    expect(buttons).toHaveLength(3);
    expect(buttons[0]).toBeDisabled();

    // Expect to be enabled after loading files
    await awaitActiveViewButton();
  });

  it('should render side panel when clicking view button', async () => {
    renderPanel();

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    const activeViewButton = await awaitActiveViewButton();
    await user.click(activeViewButton);

    // Small delay to allow React state updates to propagate - not great but fixes the test flakiness
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await waitFor(
      () => {
        return expect(screen.getByRole('dialog')).toBeInTheDocument();
      },
      { timeout: 5000 }
    );
  });

  it('should close side panel when clicking close button', async () => {
    renderPanel();

    const activeViewButton = await awaitActiveViewButton();
    await user.click(activeViewButton);

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    await waitFor(
      () => {
        return expect(screen.getByRole('dialog')).toBeInTheDocument();
      },
      { timeout: 5000 }
    );

    const closeButton = screen.getByRole('button', { name: 'Close Side Panel' });
    await user.click(closeButton);

    // Wait for dialog to close
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument(), {
      timeout: 3000,
    });
  });
});
