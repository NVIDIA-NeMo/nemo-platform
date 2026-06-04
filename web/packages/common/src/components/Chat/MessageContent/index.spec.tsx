// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MessageContent } from '@nemo/common/src/components/Chat/MessageContent';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('MessageContent', () => {
  it('renders markdown tables with sortable data-view table components', async () => {
    render(
      <MessageContent
        content={[
          '| Name | Status |',
          '| --- | --- |',
          '| Code blocks | Pretty |',
          '| Agent chat | Ready |',
        ].join('\n')}
      />
    );

    const table = screen.getByRole('table');
    const user = userEvent.setup();

    expect(screen.getByTestId('data-view-content')).toBeInTheDocument();
    expect(table).toHaveClass('nv-table-root');
    expect(table).toHaveClass('min-h-0');
    expect(within(table).getByRole('columnheader', { name: 'Name' })).toBeInTheDocument();
    expect(within(table).getByRole('columnheader', { name: 'Status' })).toBeInTheDocument();
    expect(within(table).getByRole('cell', { name: 'Agent chat' })).toBeInTheDocument();
    expect(within(table).getByRole('cell', { name: 'Ready' })).toBeInTheDocument();
    expect(within(table).getByRole('cell', { name: 'Code blocks' })).toBeInTheDocument();
    expect(within(table).getByRole('cell', { name: 'Pretty' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Filter/i })).not.toBeInTheDocument();

    expect(within(table).getAllByRole('row')[1]).toHaveTextContent('Code blocks');

    await user.click(screen.getByRole('button', { name: /Name/i }));

    expect(within(table).getAllByRole('row')[1]).toHaveTextContent('Agent chat');

    await user.type(screen.getByPlaceholderText('Search table'), 'Agent');

    await waitFor(() => {
      expect(within(table).getByRole('cell', { name: 'Agent chat' })).toBeInTheDocument();
      expect(within(table).queryByRole('cell', { name: 'Code blocks' })).not.toBeInTheDocument();
    });
  });
});
