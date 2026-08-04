// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_PAGE_SIZE } from '@nemo/common/src/constants/pagination';
import {
  GUARDRAIL_CHECKS_ENTITY_TYPE,
  type GuardrailCheckEntity,
  type Verdict,
} from '@studio/api/guardrail-checks/types';
import {
  type GuardrailCheckDetail,
  GuardrailChecksDataView,
  type GuardrailChecksDataViewProps,
} from '@studio/components/dataViews/GuardrailChecksDataView';
import { XL_SELECTOR_TIMEOUT } from '@studio/tests/util/constants';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { type FC, useState } from 'react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';

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

/** Straddles ALLOWED, so filtering to Guarded leaves a gap in the underlying array. */
const SECOND_GUARDED = makeCheck({
  id: 'chk-guarded-2',
  input: 'My card number is 4111 1111 1111 1111',
  output: 'I cannot help with that either',
  status: 'blocked',
});
const CHECKS_WITH_GAP = [GUARDED, ALLOWED, SECOND_GUARDED];

/** Renders the detail context as text, so assertions can read it off the DOM. */
const DetailProbe: FC<GuardrailCheckDetail> = ({
  check,
  checkIndex,
  visibleIndex,
  visibleCount,
  onNavigate,
}) => (
  <div>
    <span data-testid="detail-id">{check.id}</span>
    <span data-testid="detail-number">Test {checkIndex + 1}</span>
    <span data-testid="detail-position">
      {visibleIndex === null ? 'not shown' : `${visibleIndex + 1} of ${visibleCount}`}
    </span>
    <button type="button" onClick={() => onNavigate((visibleIndex ?? 0) + 1)}>
      next
    </button>
    <button type="button" onClick={() => onNavigate(visibleCount - 1)}>
      last
    </button>
  </div>
);

const renderComponent = (
  checks: GuardrailCheckEntity[] = CHECKS,
  renderDetail?: GuardrailChecksDataViewProps['renderDetail']
) => {
  const router = createMemoryRouter([
    { path: '/', element: <GuardrailChecksDataView checks={checks} renderDetail={renderDetail} /> },
  ]);

  return render(
    <TestProviders>
      <RouterProvider router={router} />
    </TestProviders>
  );
};

const renderWithDetail = (checks: GuardrailCheckEntity[] = CHECKS) =>
  renderComponent(checks, (detail) => <DetailProbe {...detail} />);

const filterToGuarded = async () => {
  fireEvent.click(screen.getByTestId('open-filters-button'));
  fireEvent.click(await screen.findByTestId('column-filter-status'));
  fireEvent.click(await screen.findByRole('option', { name: 'Guarded' }));
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

  describe('detail selection', () => {
    it('renders no detail until a row is clicked', async () => {
      renderWithDetail();

      await screen.findByText('Hello there', undefined, { timeout: XL_SELECTOR_TIMEOUT });
      expect(screen.queryByTestId('detail-id')).not.toBeInTheDocument();
    });

    it('numbers the clicked row by its place in the full list, not the visible one', async () => {
      renderWithDetail(CHECKS_WITH_GAP);

      await screen.findByText('What is the weather today', undefined, {
        timeout: XL_SELECTOR_TIMEOUT,
      });
      await filterToGuarded();
      await waitFor(
        () => expect(screen.queryByText('What is the weather today')).not.toBeInTheDocument(),
        { timeout: XL_SELECTOR_TIMEOUT }
      );

      fireEvent.click(screen.getByText('My card number is 4111 1111 1111 1111'));

      // Second of the two visible rows, but still the third test overall.
      expect(screen.getByTestId('detail-position')).toHaveTextContent('2 of 2');
      expect(screen.getByTestId('detail-number')).toHaveTextContent('Test 3');
    });

    it('walks the rows the table is showing, skipping filtered-out checks', async () => {
      renderWithDetail(CHECKS_WITH_GAP);

      await screen.findByText('What is the weather today', undefined, {
        timeout: XL_SELECTOR_TIMEOUT,
      });
      await filterToGuarded();
      await waitFor(
        () => expect(screen.queryByText('What is the weather today')).not.toBeInTheDocument(),
        { timeout: XL_SELECTOR_TIMEOUT }
      );

      fireEvent.click(screen.getByText('My SSN is 123-45-6789'));
      expect(screen.getByTestId('detail-id')).toHaveTextContent('chk-guarded');
      expect(screen.getByTestId('detail-position')).toHaveTextContent('1 of 2');

      fireEvent.click(screen.getByRole('button', { name: 'next' }));

      // The next *visible* row, not checks[1] (chk-allowed) — which the filter hid.
      expect(screen.getByTestId('detail-id')).toHaveTextContent('chk-guarded-2');
      expect(screen.getByTestId('detail-position')).toHaveTextContent('2 of 2');
    });

    it('drops navigation when the selected check is filtered out from under it', async () => {
      renderWithDetail(CHECKS_WITH_GAP);

      await screen.findByText('What is the weather today', undefined, {
        timeout: XL_SELECTOR_TIMEOUT,
      });
      fireEvent.click(screen.getByText('What is the weather today'));
      expect(screen.getByTestId('detail-position')).toHaveTextContent('2 of 3');

      await filterToGuarded();

      // The check leaves the table but stays on screen; only its position is gone.
      await waitFor(
        () => expect(screen.getByTestId('detail-position')).toHaveTextContent('not shown'),
        { timeout: XL_SELECTOR_TIMEOUT }
      );
      expect(screen.getByTestId('detail-id')).toHaveTextContent('chk-allowed');
    });

    it('pages the table along when navigation crosses a page boundary', async () => {
      // One more check than fits on a page, so the last row starts off-screen.
      const many = Array.from({ length: DEFAULT_PAGE_SIZE + 1 }, (_, i) =>
        makeCheck({ id: `chk-${i}`, input: `Test input ${i}` })
      );
      const lastInput = `Test input ${DEFAULT_PAGE_SIZE}`;
      renderWithDetail(many);

      await screen.findByText('Test input 0', undefined, { timeout: XL_SELECTOR_TIMEOUT });
      expect(screen.queryByText(lastInput)).not.toBeInTheDocument();

      fireEvent.click(screen.getByText('Test input 0'));
      fireEvent.click(screen.getByRole('button', { name: 'last' }));

      expect(screen.getByTestId('detail-id')).toHaveTextContent(`chk-${DEFAULT_PAGE_SIZE}`);
      // The table follows, so the detailed row is the one sitting behind the panel.
      expect(
        await screen.findByText(lastInput, undefined, { timeout: XL_SELECTOR_TIMEOUT })
      ).toBeInTheDocument();
    });

    it('keeps the detail on the same check when a refetch reorders the list', async () => {
      // Running the tests invalidates the checks query, so neither the array
      // identity nor its order is guaranteed to survive.
      const Harness: FC = () => {
        const [checks, setChecks] = useState(CHECKS);
        return (
          <>
            <button type="button" onClick={() => setChecks([NOT_RUN, GUARDED, ALLOWED])}>
              refetch
            </button>
            <GuardrailChecksDataView
              checks={checks}
              renderDetail={(detail) => <DetailProbe {...detail} />}
            />
          </>
        );
      };

      const router = createMemoryRouter([{ path: '/', element: <Harness /> }]);
      render(
        <TestProviders>
          <RouterProvider router={router} />
        </TestProviders>
      );

      await screen.findByText('Hello there', undefined, { timeout: XL_SELECTOR_TIMEOUT });
      fireEvent.click(screen.getByText('My SSN is 123-45-6789'));
      expect(screen.getByTestId('detail-id')).toHaveTextContent('chk-guarded');
      expect(screen.getByTestId('detail-number')).toHaveTextContent('Test 1');

      fireEvent.click(screen.getByRole('button', { name: 'refetch' }));

      // Same check, renumbered — not whatever slid into the position it held.
      expect(screen.getByTestId('detail-id')).toHaveTextContent('chk-guarded');
      expect(screen.getByTestId('detail-number')).toHaveTextContent('Test 2');
    });
  });
});
