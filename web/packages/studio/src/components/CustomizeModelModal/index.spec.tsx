// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CustomizeModelModal } from '@studio/components/CustomizeModelModal';
import { CUSTOMIZATION_METHODS } from '@studio/components/CustomizeModelModal/constants';
import { ROUTES } from '@studio/constants/routes';
import { workspace1 } from '@studio/mocks/entity-store/projects';
import { getNewCustomizationJobRoute, getPromptTuningFormRoute } from '@studio/routes/utils';
import { LOCATION_DISPLAY_TEST_ID } from '@studio/tests/util/constants';
import { LocationDisplay } from '@studio/tests/util/LocationDisplay';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

const mockOnClose = vi.fn();

interface RenderModalOptions {
  open?: boolean;
  canFineTune?: boolean;
  canPromptTune?: boolean;
  modelRef?: string;
}

const renderModal = ({
  open = true,
  canFineTune,
  canPromptTune,
  modelRef,
}: RenderModalOptions = {}) => {
  const router = createMemoryRouter(
    [
      {
        path: ROUTES.workspace.customizationJobList,
        element: (
          <CustomizeModelModal
            open={open}
            onClose={mockOnClose}
            workspace={workspace1.workspace}
            canFineTune={canFineTune}
            canPromptTune={canPromptTune}
            modelRef={modelRef}
          />
        ),
      },
      { path: getNewCustomizationJobRoute(workspace1.workspace), element: <LocationDisplay /> },
      { path: getPromptTuningFormRoute(workspace1.workspace), element: <LocationDisplay /> },
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

describe('CustomizeModelModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the modal heading and instruction text', () => {
    renderModal();
    expect(screen.getByText('Customize a Model')).toBeInTheDocument();
    expect(
      screen.getByText(
        'Select a method to use for customizing your model for your specific use case.'
      )
    ).toBeInTheDocument();
  });

  it.each(CUSTOMIZATION_METHODS)(
    'renders "$title" as an accessible radio with its tags and description',
    (method) => {
      renderModal();
      // RadioCard uses aria-labelledby on the whole label (title + tags), so match by regex
      expect(screen.getByRole('radio', { name: new RegExp(method.title) })).toBeInTheDocument();
      for (const tag of method.tags) {
        expect(screen.getByText(tag)).toBeInTheDocument();
      }
      expect(screen.getByText(method.description)).toBeInTheDocument();
    }
  );

  it('renders Cancel and Continue buttons', () => {
    renderModal();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument();
  });

  it('calls onClose when Cancel is clicked', async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it('navigates to the new customization route when fine-tuned is selected and Continue is clicked', async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    const location = (await screen.findByTestId(LOCATION_DISPLAY_TEST_ID)).textContent;
    expect(location).toEqual(getNewCustomizationJobRoute(workspace1.workspace));
    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it('navigates to the new model route when prompt tuned is selected and Continue is clicked', async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(screen.getByRole('radio', { name: /Prompt Tuned/ }));
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    const location = (await screen.findByTestId(LOCATION_DISPLAY_TEST_ID)).textContent;
    expect(location).toEqual(getPromptTuningFormRoute(workspace1.workspace));
    expect(mockOnClose).toHaveBeenCalledTimes(1);
  });

  it('navigates to the customization route after switching back to fine-tuned', async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(screen.getByRole('radio', { name: /Prompt Tuned/ }));
    await user.click(screen.getByRole('radio', { name: /Fine-Tuned/ }));
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    const location = (await screen.findByTestId(LOCATION_DISPLAY_TEST_ID)).textContent;
    expect(location).toEqual(getNewCustomizationJobRoute(workspace1.workspace));
  });

  it('does not render modal content when open is false', () => {
    renderModal({ open: false });
    expect(
      screen.queryByText(
        'Select a method to use for customizing your model for your specific use case.'
      )
    ).not.toBeInTheDocument();
  });

  it('disables the fine-tuned option when canFineTune is false', () => {
    renderModal({ canFineTune: false });
    expect(screen.getByRole('radio', { name: /Fine-Tuned/ })).toBeDisabled();
    expect(screen.getByRole('radio', { name: /Prompt Tuned/ })).not.toBeDisabled();
  });

  it('disables the prompt-tuned option when canPromptTune is false', () => {
    renderModal({ canPromptTune: false });
    expect(screen.getByRole('radio', { name: /Prompt Tuned/ })).toBeDisabled();
    expect(screen.getByRole('radio', { name: /Fine-Tuned/ })).not.toBeDisabled();
  });

  it('defaults selection to prompt-tuned when fine-tuning is disabled', async () => {
    const user = userEvent.setup();
    renderModal({ canFineTune: false });
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    const location = (await screen.findByTestId(LOCATION_DISPLAY_TEST_ID)).textContent;
    expect(location).toEqual(getPromptTuningFormRoute(workspace1.workspace));
  });

  it('disables Continue when neither method is eligible', () => {
    renderModal({ canFineTune: false, canPromptTune: false });
    expect(screen.getByRole('button', { name: 'Continue' })).toBeDisabled();
  });

  it('forwards modelRef as a ?model= query param when navigating to the fine-tune route', async () => {
    const user = userEvent.setup();
    renderModal({ modelRef: `${workspace1.workspace}/my-model` });
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    const location = (await screen.findByTestId(LOCATION_DISPLAY_TEST_ID)).textContent;
    expect(location).toEqual(
      getNewCustomizationJobRoute(workspace1.workspace, {
        model: `${workspace1.workspace}/my-model`,
      })
    );
  });

  it('forwards modelRef as a ?model= query param when navigating to the prompt-tune route', async () => {
    const user = userEvent.setup();
    renderModal({ modelRef: `${workspace1.workspace}/my-model` });
    await user.click(screen.getByRole('radio', { name: /Prompt Tuned/ }));
    await user.click(screen.getByRole('button', { name: 'Continue' }));
    const location = (await screen.findByTestId(LOCATION_DISPLAY_TEST_ID)).textContent;
    expect(location).toEqual(
      getPromptTuningFormRoute(workspace1.workspace, {
        model: `${workspace1.workspace}/my-model`,
      })
    );
  });
});
