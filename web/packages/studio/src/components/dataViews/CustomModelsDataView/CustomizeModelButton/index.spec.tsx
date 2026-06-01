// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { CustomizeModelButton } from '@studio/components/dataViews/CustomModelsDataView/CustomizeModelButton';
import { ROUTES } from '@studio/constants/routes';
import { useModelCustomizationEligibility } from '@studio/hooks/useModelCustomizationEligibility';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

vi.mock('@studio/hooks/useModelCustomizationEligibility', () => ({
  useModelCustomizationEligibility: vi.fn(),
}));

const mockedUseEligibility = vi.mocked(useModelCustomizationEligibility);

const testModel = { id: 'model-1', name: 'my-model', workspace: 'ws' } as ModelEntity;

const setEligibility = (overrides: {
  canFineTune?: boolean;
  canPromptTune?: boolean;
  isLoading?: boolean;
}) => {
  const canFineTune = overrides.canFineTune ?? false;
  const canPromptTune = overrides.canPromptTune ?? false;
  mockedUseEligibility.mockReturnValue({
    canFineTune,
    canPromptTune,
    canCustomize: canFineTune || canPromptTune,
    isLoading: overrides.isLoading ?? false,
  });
};

const renderRoute = (props: { model?: ModelEntity } = {}) => {
  const router = createMemoryRouter(
    [
      {
        path: ROUTES.workspace.customizationJobList,
        element: <CustomizeModelButton workspace={workspace1.workspace} model={props.model} />,
      },
    ],
    {
      initialEntries: [ROUTES.workspace.customizationJobList],
    }
  );
  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe('CustomizeModelButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setEligibility({ canFineTune: true, canPromptTune: true });
  });

  describe('workspace-level (no model)', () => {
    it('renders "Customize a Model"', () => {
      renderRoute();
      expect(screen.getByRole('button', { name: 'Customize a Model' })).toBeInTheDocument();
    });

    it('opens the customize model modal on click', async () => {
      const user = userEvent.setup();
      renderRoute();
      await user.click(screen.getByRole('button', { name: 'Customize a Model' }));
      expect(
        await screen.findByText(
          'Select a method to use for customizing your model for your specific use case.'
        )
      ).toBeInTheDocument();
    });

    it('stays enabled regardless of eligibility and does not gate modal options', async () => {
      setEligibility({ canFineTune: false, canPromptTune: false });
      const user = userEvent.setup();
      renderRoute();
      const button = screen.getByRole('button', { name: 'Customize a Model' });
      expect(button).not.toBeDisabled();
      await user.click(button);
      expect(await screen.findByRole('radio', { name: /Fine-Tuned/ })).not.toHaveAttribute(
        'data-disabled'
      );
      expect(screen.getByRole('radio', { name: /Prompt Tuned/ })).not.toHaveAttribute(
        'data-disabled'
      );
    });
  });

  describe('per-model', () => {
    it('renders "Customize this Model" when a model is provided', () => {
      renderRoute({ model: testModel });
      expect(screen.getByRole('button', { name: /Customize this Model/ })).toBeInTheDocument();
    });

    it('disables the button while eligibility is loading', () => {
      setEligibility({ isLoading: true });
      renderRoute({ model: testModel });
      expect(screen.getByRole('button', { name: /Customize this Model/ })).toBeDisabled();
    });

    it('shows a spinner while eligibility is loading', () => {
      setEligibility({ isLoading: true });
      renderRoute({ model: testModel });
      expect(screen.getByRole('status')).toBeInTheDocument();
    });

    it('disables the button when neither method is eligible', () => {
      setEligibility({ canFineTune: false, canPromptTune: false });
      renderRoute({ model: testModel });
      expect(screen.getByRole('button', { name: /Customize this Model/ })).toBeDisabled();
    });

    it('enables the button when at least one method is eligible', () => {
      setEligibility({ canFineTune: true, canPromptTune: false });
      renderRoute({ model: testModel });
      expect(screen.getByRole('button', { name: /Customize this Model/ })).not.toBeDisabled();
    });

    it('forwards eligibility into the modal so ineligible options are disabled', async () => {
      setEligibility({ canFineTune: false, canPromptTune: true });
      const user = userEvent.setup();
      renderRoute({ model: testModel });
      await user.click(screen.getByRole('button', { name: /Customize this Model/ }));
      expect(await screen.findByRole('radio', { name: /Fine-Tuned/ })).toBeDisabled();
      expect(screen.getByRole('radio', { name: /Prompt Tuned/ })).not.toBeDisabled();
    });
  });
});
