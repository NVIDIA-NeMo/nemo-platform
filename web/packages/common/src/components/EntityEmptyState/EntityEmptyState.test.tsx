// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { EntityEmptyState } from '@nemo/common/src/components/EntityEmptyState';
import { ENTITY_EMPTY_STATES } from '@nemo/common/src/components/EntityEmptyState/registry';
import { ToastProvider } from '@nemo/common/src/providers/toast/ToastProvider';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FC, ReactNode } from 'react';
import { MemoryRouter } from 'react-router';

const wrap = (ui: ReactNode) =>
  render(
    <MemoryRouter>
      <ToastProvider>{ui}</ToastProvider>
    </MemoryRouter>
  );

const Guardrails: FC<Partial<React.ComponentProps<typeof EntityEmptyState>>> = (props) => (
  <EntityEmptyState entity="guardrails" variant="first-use" {...props} />
);

describe('EntityEmptyState', () => {
  const descriptor = ENTITY_EMPTY_STATES.guardrails;

  describe('first-use', () => {
    it('renders registry heading, subheading, and the CLI / prompt copy rows', () => {
      wrap(<Guardrails onCreate={vi.fn()} />);

      expect(screen.getByText(descriptor.heading)).toBeInTheDocument();
      expect(screen.getByText(descriptor.subheading)).toBeInTheDocument();
      expect(screen.getByText(descriptor.cliCommand as string)).toBeInTheDocument();
      expect(screen.getByText(descriptor.skillPrompt as string)).toBeInTheDocument();
    });

    it('invokes onCreate from the primary CTA', async () => {
      const onCreate = vi.fn();
      wrap(<Guardrails onCreate={onCreate} />);

      await userEvent.click(
        screen.getByRole('button', { name: descriptor.createAction?.label })
      );
      expect(onCreate).toHaveBeenCalledTimes(1);
    });

    it('omits the create CTA when neither onCreate nor a route is available', () => {
      wrap(<Guardrails />);

      expect(
        screen.queryByRole('button', { name: descriptor.createAction?.label })
      ).not.toBeInTheDocument();
    });

    it('copies the CLI command to the clipboard', async () => {
      const user = userEvent.setup();
      wrap(<Guardrails onCreate={vi.fn()} />);

      await user.click(screen.getByRole('button', { name: 'Copy CLI command' }));
      expect(await navigator.clipboard.readText()).toBe(descriptor.cliCommand);
    });
  });

  describe('no-results', () => {
    it('shows the clear-filters action and hides the create CTA', async () => {
      const onClearFilters = vi.fn();
      wrap(<Guardrails variant="no-results" onCreate={vi.fn()} onClearFilters={onClearFilters} />);

      expect(screen.getByText('No results found')).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: descriptor.createAction?.label })
      ).not.toBeInTheDocument();

      await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
      expect(onClearFilters).toHaveBeenCalledTimes(1);
    });
  });

  describe('error', () => {
    it('shows the retry action', async () => {
      const onRetry = vi.fn();
      wrap(<Guardrails variant="error" onRetry={onRetry} />);

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
      expect(onRetry).toHaveBeenCalledTimes(1);
    });
  });
});
