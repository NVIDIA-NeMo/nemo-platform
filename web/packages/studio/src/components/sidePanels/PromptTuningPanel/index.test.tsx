// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { render, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

import { PromptTuningPanel } from '.';

describe('PromptTuningPanel', () => {
  const mockProject = 'test-project';
  const mockModel: ModelEntity = {
    id: 'model-test-id',
    name: 'test-model',
    workspace: 'test-namespace',
    base_model: 'llama-2-7b-chat',
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
    prompt: {
      system_prompt: 'You are a helpful assistant.',
      icl_few_shot_examples: 'Example 1: Input -> Output',
    },
  };

  it('renders with loading state', () => {
    render(<PromptTuningPanel workspace={mockProject} isLoading open onOpenChange={() => {}} />);

    expect(screen.getByTestId('spinner')).toBeInTheDocument();
  });

  it('renders with no model', () => {
    render(
      <PromptTuningPanel workspace={mockProject} isLoading={false} open onOpenChange={() => {}} />
    );

    expect(screen.getByRole('tab', { name: 'Chat Playground' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Model Details' })).toBeInTheDocument();
    expect(screen.getByText('Awaiting Model Selection')).toBeInTheDocument();
    expect(screen.getByText('Select a base model to get started')).toBeInTheDocument();
  });

  it('renders with model data', () => {
    render(
      <PromptTuningPanel
        workspace={mockProject}
        model={mockModel}
        isLoading={false}
        open
        onOpenChange={() => {}}
      />
    );

    expect(screen.getByRole('tab', { name: 'Chat Playground' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Model Details' })).toBeInTheDocument();
    // The ModelChat component should render when a model is provided
    expect(screen.queryByText('Awaiting Model Selection')).not.toBeInTheDocument();
  });

  it('renders with model data in details tab', async () => {
    const user = userEvent.setup();

    render(
      <PromptTuningPanel
        workspace={mockProject}
        model={mockModel}
        isLoading={false}
        open
        onOpenChange={() => {}}
      />
    );

    const chatTab = screen.getByRole('tab', { name: 'Chat Playground' });
    const detailsTab = screen.getByRole('tab', { name: 'Model Details' });
    expect(chatTab).toBeInTheDocument();
    expect(detailsTab).toBeInTheDocument();

    await user.click(detailsTab);

    expect(screen.queryByText('Awaiting Model Selection')).not.toBeInTheDocument();
    expect(screen.getByText('You are a helpful assistant.')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument(); // default temperature
    expect(screen.getByText('1024')).toBeInTheDocument(); // default max_tokens
  });

  // TODO: Update these tests after artifact status logic is reimplemented
  // The artifact property was removed from ModelEntity in the API update
  it.skip('renders with deployment in progress message when model is pending', async () => {
    render(
      <PromptTuningPanel
        workspace={mockProject}
        model={mockModel}
        isLoading={false}
        open
        onOpenChange={() => {}}
      />
    );

    expect(screen.queryByText('Awaiting Model Selection')).not.toBeInTheDocument();
    expect(screen.getByText('Model Deployment in Progress')).toBeInTheDocument();
    expect(
      screen.getByText('Check back in a few minutes to chat with this model.')
    ).toBeInTheDocument();
  });

  it.skip('renders with chat unavailable message when model deployment failed', async () => {
    render(
      <PromptTuningPanel
        workspace={mockProject}
        model={mockModel}
        isLoading={false}
        open
        onOpenChange={() => {}}
      />
    );

    expect(screen.queryByText('Awaiting Model Selection')).not.toBeInTheDocument();
    expect(screen.getByText('Chat Unavailable')).toBeInTheDocument();
    expect(screen.getByText('Real time chat is unavailable for this model.')).toBeInTheDocument();
  });
});
