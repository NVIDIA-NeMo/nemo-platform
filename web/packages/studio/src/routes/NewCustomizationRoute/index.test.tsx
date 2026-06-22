// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { workspace1 } from '@studio/mocks/entity-store/projects';
import { NewCustomizationRoute } from '@studio/routes/NewCustomizationRoute';
import { mockUseNavigate, mockUseParams } from '@studio/tests/util/mockUseParams';
import { render, screen } from '@studio/tests/util/render';
import { TestProviders } from '@studio/tests/util/TestProviders';

const renderRoute = () => {
  return render(
    <TestProviders>
      <NewCustomizationRoute />
    </TestProviders>
  );
};

describe('NewCustomizationRoute', () => {
  beforeEach(() => {
    mockUseParams({
      workspace: workspace1.workspace,
    });
    mockUseNavigate();
  });

  it('Renders the customization form', async () => {
    renderRoute();

    // Verify the form renders with the correct heading
    const heading = await screen.findByText('Fine-tune a Model');
    expect(heading).toBeInTheDocument();

    // Verify the model selector is present
    const modelSelector = await screen.findByTestId('base-model-select');
    expect(modelSelector).toBeInTheDocument();
  });

  it('Renders hyperparameters accordion', async () => {
    renderRoute();

    // CustomizationHyperparameters is always rendered in the form
    const hyperparametersAccordion = await screen.findByText('Show Advanced Training Parameters');
    expect(hyperparametersAccordion).toBeInTheDocument();
  });
});
