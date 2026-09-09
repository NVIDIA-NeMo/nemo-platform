// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ResultsPreviewPanel } from '@studio/routes/AnonymizerJobDetailRoute/components/ResultsPreviewPanel';
import { fireEvent, render, screen, within } from '@studio/tests/util/render';

vi.mock('@studio/routes/AnonymizerJobDetailRoute/useResultPreview', () => ({
  useResultPreview: () => ({
    rows: [
      { text: 'Hello John', text_replaced: 'Hello [NAME]' },
      { text: 'Hello Jane', text_replaced: 'Hello [NAME]' },
    ],
    textColumn: 'text',
    isLoading: false,
    error: null,
  }),
}));

describe('ResultsPreviewPanel', () => {
  it('opens the record preview modal when a row is selected', async () => {
    render(<ResultsPreviewPanel workspace="default" artifactUrl="default/job#results" />);

    fireEvent.click(screen.getByText('Hello John'));

    const modal = within(await screen.findByRole('dialog'));
    expect(modal.getByText('Record Preview')).toBeInTheDocument();
    expect(modal.getByText('Hello John')).toBeInTheDocument();
    expect(modal.getByText('Hello [NAME]')).toBeInTheDocument();
  });

  it('opens the record preview modal from the Details button', async () => {
    render(<ResultsPreviewPanel workspace="default" artifactUrl="default/job#results" />);

    fireEvent.click(screen.getAllByRole('button', { name: 'Details' })[0]);

    const modal = within(await screen.findByRole('dialog'));
    expect(modal.getByText('Record Preview')).toBeInTheDocument();
  });

  it('navigates between records with the pager', async () => {
    render(<ResultsPreviewPanel workspace="default" artifactUrl="default/job#results" />);

    fireEvent.click(screen.getAllByRole('button', { name: 'Details' })[0]);

    const modal = within(await screen.findByRole('dialog'));
    expect(modal.getByText('Record 1 of 2')).toBeInTheDocument();
    expect(modal.getByText('Hello John')).toBeInTheDocument();

    fireEvent.click(modal.getByRole('button', { name: 'Next record' }));

    expect(modal.getByText('Record 2 of 2')).toBeInTheDocument();
    expect(modal.getByText('Hello Jane')).toBeInTheDocument();
  });
});
