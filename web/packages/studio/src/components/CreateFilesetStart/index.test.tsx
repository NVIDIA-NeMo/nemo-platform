// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useModelsListProviders } from '@nemo/sdk/generated/platform/api';
import { CreateFilesetStart } from '@studio/components/CreateFilesetStart';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('@studio/hooks/useWorkspaceFromPath', () => ({
  useWorkspaceFromPath: () => 'default',
}));

vi.mock('@nemo/sdk/generated/platform/api', () => ({
  useModelsListProviders: vi.fn(),
}));

const mockUseModelsListProviders = vi.mocked(useModelsListProviders);

/** A provider list containing the NVIDIA Build (integrate.api.nvidia.com) endpoint. */
const withBuildProvider = () =>
  ({
    data: { data: [{ host_url: 'https://integrate.api.nvidia.com/v1' }] },
    isLoading: false,
  }) as unknown as ReturnType<typeof useModelsListProviders>;

/** A provider list with only a non-build provider. */
const withoutBuildProvider = () =>
  ({
    data: { data: [{ host_url: 'https://api.openai.com/v1' }] },
    isLoading: false,
  }) as unknown as ReturnType<typeof useModelsListProviders>;

const renderComponent = (onContinue = vi.fn()) =>
  render(
    <MemoryRouter>
      <CreateFilesetStart onContinue={onContinue} />
    </MemoryRouter>
  );

describe('CreateFilesetStart', () => {
  beforeEach(() => {
    mockUseModelsListProviders.mockReturnValue(withBuildProvider());
  });

  it('renders all four start options', () => {
    renderComponent();

    expect(screen.getByText('Describe with AI')).toBeInTheDocument();
    expect(screen.getByText('Start from a template')).toBeInTheDocument();
    expect(screen.getByText('Build from scratch')).toBeInTheDocument();
  });

  it('shows no Continue footer until a selectable option is chosen', () => {
    renderComponent();

    expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
  });

  it('does not select disabled options (they are no-ops)', async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();
    renderComponent(onContinue);

    await user.click(screen.getByText('Describe with AI'));

    expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
    expect(onContinue).not.toHaveBeenCalled();
  });

  it('selecting Build from scratch reveals Continue and invokes onContinue with "scratch"', async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();
    renderComponent(onContinue);

    await user.click(screen.getByText('Build from scratch'));

    const continueButton = screen.getByRole('button', { name: /continue/i });
    expect(continueButton).toBeInTheDocument();

    await user.click(continueButton);
    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onContinue).toHaveBeenCalledWith('scratch');
  });

  it('reveals template cards but no Continue until a template is chosen', async () => {
    const user = userEvent.setup();
    renderComponent();

    await user.click(screen.getByText('Start from a template'));

    expect(screen.getByText('Instruction fine-tuning (SFT)')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
  });

  it('choosing a template reveals Continue and invokes onContinue with the template id', async () => {
    const user = userEvent.setup();
    const onContinue = vi.fn();
    renderComponent(onContinue);

    await user.click(screen.getByText('Start from a template'));
    await user.click(screen.getByText('Instruction fine-tuning (SFT)'));

    const continueButton = screen.getByRole('button', { name: /continue/i });
    await user.click(continueButton);

    expect(onContinue).toHaveBeenCalledTimes(1);
    expect(onContinue).toHaveBeenCalledWith('template', 'sft-instruction');
  });

  it('switching options clears a prior template selection', async () => {
    const user = userEvent.setup();
    renderComponent();

    await user.click(screen.getByText('Start from a template'));
    await user.click(screen.getByText('Instruction fine-tuning (SFT)'));
    expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument();

    await user.click(screen.getByText('Build from scratch'));
    await user.click(screen.getByText('Start from a template'));

    // Template selection was reset when the option changed, so Continue is gone again.
    expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();
  });

  describe('when no NVIDIA Build inference provider is configured', () => {
    beforeEach(() => {
      mockUseModelsListProviders.mockReturnValue(withoutBuildProvider());
    });

    it('disables LLM-backed templates and shows a link to add the provider', async () => {
      const user = userEvent.setup();
      const onContinue = vi.fn();
      renderComponent(onContinue);

      await user.click(screen.getByText('Start from a template'));

      // LLM template (SFT references a model) is disabled and cannot be selected.
      const sftCard = screen.getByRole('button', { name: /Instruction fine-tuning/i });
      expect(sftCard).toBeDisabled();
      await user.click(sftCard);
      expect(screen.queryByRole('button', { name: /continue/i })).not.toBeInTheDocument();

      // Error label links to the inference-providers create view (build preset).
      const link = screen.getByRole('link', { name: /Add the NVIDIA Build provider/i });
      expect(link).toHaveAttribute(
        'href',
        expect.stringContaining('/inference-providers?create=true&preset=build')
      );
    });

    it('keeps non-LLM templates enabled and selectable', async () => {
      const user = userEvent.setup();
      const onContinue = vi.fn();
      renderComponent(onContinue);

      await user.click(screen.getByText('Start from a template'));

      const noLlmCard = screen.getByRole('button', { name: /Expression transforms/i });
      expect(noLlmCard).toBeEnabled();

      await user.click(noLlmCard);
      const continueButton = screen.getByRole('button', { name: /continue/i });
      await user.click(continueButton);
      expect(onContinue).toHaveBeenCalledWith('template', 'expression-transforms');
    });
  });
});
