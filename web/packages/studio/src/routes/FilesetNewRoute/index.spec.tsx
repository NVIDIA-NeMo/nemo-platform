// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ROUTE_PARAMS } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { FilesetNewRoute } from '@studio/routes/FilesetNewRoute';
import { mockUseNavigate, mockUseParams } from '@studio/tests/util/mockUseParams';
import { render, screen } from '@studio/tests/util/render';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const renderRoute = () => {
  return render(
    <TestProviders>
      <FilesetNewRoute />
    </TestProviders>
  );
};

describe('FilesetNewRoute', () => {
  beforeEach(() => {
    mockUseParams({
      [ROUTE_PARAMS.workspace]: workspace1.workspace,
    });
    mockUseNavigate();
  });

  it('renders the side panel with Create Fileset heading', async () => {
    renderRoute();

    const heading = await screen.findByTestId('nv-side-panel-heading');
    expect(heading).toHaveTextContent('Create Fileset');
  });

  it('renders Custom Fileset and Sample Dataset tabs', async () => {
    renderRoute();

    expect(await screen.findByRole('radio', { name: 'Custom Fileset' })).toBeInTheDocument();
    expect(await screen.findByRole('radio', { name: 'Sample Dataset' })).toBeInTheDocument();
  });

  it('shows custom fileset form when Custom Fileset tab is selected', async () => {
    renderRoute();

    expect(await screen.findByRole('textbox', { name: 'Fileset Name' })).toBeInTheDocument();
    expect(
      await screen.findByRole('textbox', { name: 'Description (optional)' })
    ).toBeInTheDocument();
    expect(await screen.findByText('Source')).toBeInTheDocument();
    expect(await screen.findByRole('tab', { name: 'Upload' })).toBeInTheDocument();
    expect(await screen.findByRole('tab', { name: 'External' })).toBeInTheDocument();
  });

  it('renders Purpose selector with Generic, Dataset, and Model options', async () => {
    renderRoute();

    // Heading + all three radio cards render with their labels and descriptions
    expect(await screen.findByText('Purpose')).toBeInTheDocument();
    expect(await screen.findByRole('radio', { name: 'Generic' })).toBeInTheDocument();
    expect(await screen.findByRole('radio', { name: 'Dataset' })).toBeInTheDocument();
    expect(await screen.findByRole('radio', { name: 'Model' })).toBeInTheDocument();

    // The lock-in note should be visible so users know purpose is immutable
    expect(
      await screen.findByText(
        /Purpose determines which metadata fields are available and can't be changed/i
      )
    ).toBeInTheDocument();
  });

  it('defaults Purpose selection to Dataset', async () => {
    renderRoute();

    const datasetCard = await screen.findByRole('radio', { name: 'Dataset' });
    expect(datasetCard).toBeChecked();
  });

  it('shows Create Fileset and Cancel in the footer', async () => {
    renderRoute();

    expect(await screen.findByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: 'Create Fileset' })).toBeInTheDocument();
  });

  it('switches to Sample Dataset tab and shows sample dataset cards', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByText('Sample Dataset'));

    expect(
      await screen.findByText('Choose from the following pre-configured sample datasets.')
    ).toBeInTheDocument();
    expect(await screen.findByText('Q&A Generation Dataset')).toBeInTheDocument();
  });

  it('shows External storage URL and secret select when External tab is selected', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('tab', { name: 'External' }));

    expect(await screen.findByRole('textbox', { name: 'URL' })).toBeInTheDocument();
    expect(await screen.findByRole('combobox', { name: 'Secret Key' })).toBeInTheDocument();
  });

  it('opens Create Secret modal when New Secret is chosen from the secret dropdown', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('tab', { name: 'External' }));
    await user.click(await screen.findByRole('combobox', { name: 'Secret Key' }));
    await user.click(await screen.findByRole('menuitem', { name: 'New Secret' }));

    const secretDialog = await screen.findByRole('dialog', { name: 'Create Secret' });
    expect(secretDialog).toBeInTheDocument();
    await user.click(within(secretDialog).getByRole('button', { name: 'Cancel' }));
  });

  it('shows NGC API key label when External URL is an NGC catalog URL', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('tab', { name: 'External' }));

    const urlInput = await screen.findByRole('textbox', { name: 'URL' });
    await user.clear(urlInput);
    await user.type(
      urlInput,
      'https://catalog.ngc.nvidia.com/orgs/nvidia/teams/ngc-apps/resources/some-dataset'
    );

    expect(screen.getAllByText(/NGC API key/i).length).toBeGreaterThan(0);
  });

  it('shows HuggingFace token (optional) label when External URL is a Hugging Face URL', async () => {
    const user = userEvent.setup();
    renderRoute();

    await user.click(await screen.findByRole('tab', { name: 'External' }));

    const urlInput = await screen.findByRole('textbox', { name: 'URL' });
    await user.clear(urlInput);
    await user.type(urlInput, 'https://huggingface.co/datasets/org/repo-name');

    expect(screen.getAllByText(/HuggingFace token \(optional\)/i).length).toBeGreaterThan(0);
  });
});
