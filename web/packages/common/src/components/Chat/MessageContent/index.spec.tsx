// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MessageContent } from '@nemo/common/src/components/Chat/MessageContent';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const expectNoDirectParagraphChild = (listItem: HTMLElement): void => {
  // The list marker alignment depends on the first paragraph being unwrapped inside list items.
  // eslint-disable-next-line testing-library/no-node-access
  expect(listItem.querySelector(':scope > p')).not.toBeInTheDocument();
};

describe('MessageContent', () => {
  it('renders markdown headings and list items with visible list styling', () => {
    render(
      <MessageContent
        content={
          '# Overview\n\n## Plan\n\nRead the route carefully.\n\n- Read the route\n- Update the renderer\n\n### Details'
        }
      />
    );

    expect(screen.getByRole('heading', { level: 1, name: 'Overview' })).toHaveClass(
      'mb-density-sm',
      'mt-density-3xl',
      'first:mt-0'
    );
    expect(screen.getByRole('heading', { level: 2, name: 'Plan' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 2, name: 'Plan' })).toHaveClass(
      'mb-density-sm',
      'mt-density-3xl'
    );
    expect(screen.getByRole('heading', { level: 3, name: 'Details' })).toHaveClass(
      'mb-density-sm',
      'mt-density-2xl'
    );
    expect(screen.getByTestId('chat-message-content-text')).toHaveClass(
      'text-sm',
      'leading-[160%]'
    );
    expect(screen.getByTestId('chat-message-content-text')).not.toHaveClass('text-base');
    expect(screen.getByText('Read the route carefully.')).toHaveClass('mb-density-xl');
    expect(screen.getByRole('list')).toHaveClass('my-density-xl', 'list-disc');
    expect(screen.getByRole('list')).not.toHaveClass('space-y-0.5');
    const listItems = screen.getAllByRole('listitem');
    expect(listItems).toHaveLength(2);
    expect(listItems[0]).toHaveTextContent('Read the route');
    expect(listItems[0]).toHaveClass(
      'mb-density-sm',
      'whitespace-normal',
      'pl-density-xs',
      'text-sm',
      'leading-[160%]',
      'last:mb-0',
      '[&>p]:my-0'
    );
  });

  it('keeps loose ordered list content aligned with the number marker', () => {
    render(
      <MessageContent
        content={[
          '2.',
          '',
          '**First item** with a paragraph.',
          '',
          '3.',
          '',
          '**Second item** with a paragraph.',
        ].join('\n')}
      />
    );

    const orderedList = screen.getByRole('list');
    expect(screen.getByTestId('chat-message-content-text')).toHaveClass('whitespace-normal');
    expect(orderedList.tagName).toBe('OL');
    expect(orderedList).toHaveAttribute('start', '2');
    expect(orderedList).toHaveClass('my-density-xl', 'list-decimal', 'pl-density-2xl');
    expect(orderedList).not.toHaveClass('pl-density-lg');

    const listItems = within(orderedList).getAllByRole('listitem');
    expect(listItems).toHaveLength(2);
    expectNoDirectParagraphChild(listItems[0]);
    expect(listItems[0]).toHaveTextContent('First item with a paragraph.');
    expectNoDirectParagraphChild(listItems[1]);
    expect(listItems[1]).toHaveTextContent('Second item with a paragraph.');
  });

  it('keeps indented loose ordered list content aligned with the number marker', () => {
    render(
      <MessageContent
        content={[
          '2.',
          '',
          '   **TS client generation** via Orval.',
          '',
          '3.',
          '',
          '   **Custom axios fetcher.** Each generated service uses a mutator.',
        ].join('\n')}
      />
    );

    const orderedList = screen.getByRole('list');
    const listItems = within(orderedList).getAllByRole('listitem');

    expect(orderedList).toHaveAttribute('start', '2');
    expect(listItems).toHaveLength(2);
    expectNoDirectParagraphChild(listItems[0]);
    expect(listItems[0]).toHaveTextContent('TS client generation via Orval.');
    expectNoDirectParagraphChild(listItems[1]);
    expect(listItems[1]).toHaveTextContent(
      'Custom axios fetcher. Each generated service uses a mutator.'
    );
  });

  it('renders inline code with grey backgrounds and prose font', () => {
    render(<MessageContent content="Run `pnpm test` after editing." />);

    expect(screen.getByText('pnpm test')).toHaveClass(
      'bg-gray-050',
      'dark:bg-gray-800',
      'font-sans',
      'text-sm'
    );
    expect(screen.getByText('pnpm test')).not.toHaveClass('text-[0.95em]');
    expect(screen.getByText('pnpm test')).not.toHaveClass('text-base');
    expect(screen.getByText('pnpm test')).not.toHaveClass('font-mono');
  });

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
