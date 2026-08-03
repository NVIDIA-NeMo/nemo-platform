// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  GUARDRAIL_CHECKS_ENTITY_TYPE,
  type GuardrailCheckEntity,
  type Verdict,
} from '@studio/api/guardrail-checks/types';
import { GuardrailChecksDataView } from '@studio/components/dataViews/GuardrailChecksDataView';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';

const makeCheck = ({
  id,
  input,
  output,
  status,
}: {
  id: string;
  input: string;
  output?: string;
  status?: Verdict;
}): GuardrailCheckEntity => ({
  entity_type: GUARDRAIL_CHECKS_ENTITY_TYPE,
  id,
  parent: 'cfg-1',
  db_version: 1,
  name: id,
  workspace: 'default',
  created_at: '2026-04-12T11:00:00.000Z',
  created_by: 'user@example.com',
  updated_at: '2026-04-12T11:00:00.000Z',
  updated_by: 'user@example.com',
  data: {
    messages: [
      { role: 'user', content: input },
      ...(output ? [{ role: 'assistant' as const, content: output }] : []),
    ],
    runs: status
      ? [{ run_at: '2026-04-12T11:05:00.000Z', status, rails_status: {}, config_version: 1 }]
      : [],
  },
});

const GUARDED = makeCheck({
  id: 'chk-guarded',
  input: 'My SSN is 123-45-6789',
  output: 'I cannot help with that',
  status: 'blocked',
});
const ALLOWED = makeCheck({
  id: 'chk-allowed',
  input: 'What is the weather today',
  output: 'It is sunny',
  status: 'success',
});
const NOT_RUN = makeCheck({ id: 'chk-not-run', input: 'Hello there' });

const CHECKS = [GUARDED, ALLOWED, NOT_RUN];

const renderComponent = (checks: GuardrailCheckEntity[] = CHECKS) => {
  const router = createMemoryRouter([
    { path: '/', element: <GuardrailChecksDataView checks={checks} /> },
  ]);

  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

describe('GuardrailChecksDataView', () => {
  it('renders a row per check with its input and output', async () => {
    renderComponent();

    expect(
      await screen.findByText('My SSN is 123-45-6789', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    expect(screen.getByText('I cannot help with that')).toBeInTheDocument();
    expect(screen.getByText('What is the weather today')).toBeInTheDocument();
    expect(screen.getByText('Hello there')).toBeInTheDocument();
  });

  it('renders the Input, Output, and Result columns', async () => {
    renderComponent();

    for (const header of ['Input', 'Output', 'Result']) {
      expect(
        await screen.findByRole('columnheader', { name: header }, { timeout: XL_SELECTOR_TIMEOUT })
      ).toBeInTheDocument();
    }
  });

  it('maps each latest-run verdict to its result badge', async () => {
    renderComponent();

    await screen.findByText('Hello there', undefined, { timeout: XL_SELECTOR_TIMEOUT });

    const rowFor = (input: string) => screen.getByRole('row', { name: new RegExp(input) });

    expect(rowFor('My SSN is 123-45-6789')).toHaveTextContent('Guarded');
    expect(rowFor('What is the weather today')).toHaveTextContent('Allowed');
    // A check with no runs has never been evaluated — it must not read as a passing test.
    expect(rowFor('Hello there')).toHaveTextContent('Not run');
  });

  it('falls back to a dash when a check has no assistant output', async () => {
    renderComponent([NOT_RUN]);

    expect(
      await screen.findByText('Hello there', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('narrows rows to those matching the search text', async () => {
    const user = userEvent.setup();
    renderComponent();

    await screen.findByText('Hello there', undefined, { timeout: XL_SELECTOR_TIMEOUT });
    await user.type(screen.getByPlaceholderText('Search tests...'), 'weather');

    await waitFor(() => expect(screen.queryByText('Hello there')).not.toBeInTheDocument(), {
      timeout: XL_SELECTOR_TIMEOUT,
    });
    expect(screen.getByText('What is the weather today')).toBeInTheDocument();
  });

  it('searches assistant output as well as user input', async () => {
    const user = userEvent.setup();
    renderComponent();

    await screen.findByText('Hello there', undefined, { timeout: XL_SELECTOR_TIMEOUT });
    await user.type(screen.getByPlaceholderText('Search tests...'), 'cannot help');

    await waitFor(() => expect(screen.queryByText('Hello there')).not.toBeInTheDocument(), {
      timeout: XL_SELECTOR_TIMEOUT,
    });
    expect(screen.getByText('My SSN is 123-45-6789')).toBeInTheDocument();
  });

  it('filters by result and restores every row when the filter is cleared', async () => {
    renderComponent();

    await screen.findByText('Hello there', undefined, { timeout: XL_SELECTOR_TIMEOUT });

    fireEvent.click(screen.getByTestId('open-filters-button'));
    fireEvent.click(await screen.findByTestId('column-filter-status'));
    fireEvent.click(await screen.findByRole('option', { name: 'Guarded' }));

    await waitFor(() => expect(screen.queryByText('Hello there')).not.toBeInTheDocument(), {
      timeout: XL_SELECTOR_TIMEOUT,
    });
    expect(screen.getByText('My SSN is 123-45-6789')).toBeInTheDocument();
    expect(screen.queryByText('What is the weather today')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('clear-filters'));

    expect(
      await screen.findByText('Hello there', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    expect(screen.getByText('What is the weather today')).toBeInTheDocument();
  });

  it('shows the no-tests empty state when there are no checks', async () => {
    renderComponent([]);

    expect(
      await screen.findByText('No tests yet', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Clear Filters/i })).not.toBeInTheDocument();
  });

  it('offers a way out when a search matches nothing', async () => {
    const user = userEvent.setup();
    renderComponent();

    await screen.findByText('Hello there', undefined, { timeout: XL_SELECTOR_TIMEOUT });
    await user.type(screen.getByPlaceholderText('Search tests...'), 'no-such-test');

    expect(
      await screen.findByText('No Results Found', undefined, { timeout: XL_SELECTOR_TIMEOUT })
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Clear Filters/i })).toBeInTheDocument();
  });
});
