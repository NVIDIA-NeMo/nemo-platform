// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ChatThreadErrorBoundary } from '@studio/routes/agents/AssistantChatRoute/ChatThreadErrorBoundary';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';

const Boom = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) throw new Error('Failed to fetch dynamically imported module');
  return <div data-testid="chat-thread" />;
};

const renderBoundary = (shouldThrow: boolean, onRetry = vi.fn()) =>
  render(
    <TestProviders>
      <MemoryRouter>
        <ChatThreadErrorBoundary onRetry={onRetry}>
          <Boom shouldThrow={shouldThrow} />
        </ChatThreadErrorBoundary>
      </MemoryRouter>
    </TestProviders>
  );

describe('ChatThreadErrorBoundary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders children when nothing throws', () => {
    renderBoundary(false);

    expect(screen.getByTestId('chat-thread')).toBeInTheDocument();
  });

  it('renders the failure message instead of unwinding when the chunk fails to load', () => {
    renderBoundary(true);

    expect(screen.getByText('Chat failed to load')).toBeInTheDocument();
    expect(screen.queryByTestId('chat-thread')).not.toBeInTheDocument();
  });

  it('clears the error and calls onRetry when Try Again is clicked', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const { rerender } = renderBoundary(true, onRetry);

    rerender(
      <TestProviders>
        <MemoryRouter>
          <ChatThreadErrorBoundary onRetry={onRetry}>
            <Boom shouldThrow={false} />
          </ChatThreadErrorBoundary>
        </MemoryRouter>
      </TestProviders>
    );
    await user.click(screen.getByRole('button', { name: /try again/i }));

    expect(onRetry).toHaveBeenCalledOnce();
    expect(screen.getByTestId('chat-thread')).toBeInTheDocument();
  });
});
