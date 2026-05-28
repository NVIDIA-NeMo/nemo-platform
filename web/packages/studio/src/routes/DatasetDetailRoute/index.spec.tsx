// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DatasetDetailRoute } from '@studio/routes/DatasetDetailRoute';
import { render } from '@studio/tests/util/render';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render as rtlRender, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Stub the file preview content so the FilesTab spec doesn't need handlers
// for the file-content fetch. The preview component has its own spec.
vi.mock('@studio/components/FilesetFilePreviewPanel/FilesetFilePreviewContent', () => ({
  FilesetFilePreviewContent: ({ filePath }: { filePath: string }) => (
    <div data-testid="mock-file-preview-content">{filePath}</div>
  ),
}));

vi.mock('@studio/providers/workers/useWorkers', () => ({
  useWorkers: () => ({
    createWorker: vi.fn(),
  }),
}));

vi.mock('@studio/hooks/useWorkspaceFromPath', () => ({
  useWorkspaceFromPath: () => 'default',
}));

vi.mock('@studio/util/hooks/useRequiredPathParams', () => ({
  useRequiredPathParams: () => ({ datasetName: 'test-dataset' }),
}));

describe('DatasetDetailRoute', () => {
  it('renders both tabs with Dataset Card selected by default', () => {
    render(<DatasetDetailRoute />);

    expect(screen.getByRole('tab', { name: 'Dataset Card' })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    expect(screen.getByRole('tab', { name: 'Files' })).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByTestId('dataset-card-tab')).toBeInTheDocument();
  });

  it('switches to the Files tab when clicked and renders the file explorer', async () => {
    const user = userEvent.setup();
    render(<DatasetDetailRoute />);

    await user.click(screen.getByRole('tab', { name: 'Files' }));

    expect(screen.getByRole('tab', { name: 'Files' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('dataset-files-tab')).toBeInTheDocument();
  });

  const renderAtUrl = (url: string) =>
    rtlRender(
      <TestProviders>
        <MemoryRouter initialEntries={[url]}>
          <DatasetDetailRoute />
        </MemoryRouter>
      </TestProviders>
    );

  it('opens the Files tab when the initial URL has ?tab=files', () => {
    renderAtUrl('/?tab=files');

    expect(screen.getByRole('tab', { name: 'Files' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('dataset-files-tab')).toBeInTheDocument();
  });

  it('falls back to the default tab when ?tab= is an unknown value', () => {
    renderAtUrl('/?tab=garbage');

    expect(screen.getByRole('tab', { name: 'Dataset Card' })).toHaveAttribute(
      'aria-selected',
      'true'
    );
  });

  it('renders the file preview when ?file= is set on the Files tab', () => {
    renderAtUrl('/?tab=files&file=folder%2Fdata.json');

    expect(screen.getByTestId('dataset-files-tab-preview')).toBeInTheDocument();
    expect(screen.getByTestId('mock-file-preview-content')).toHaveTextContent('folder/data.json');
  });

  it('renders the explorer when no file is selected on the Files tab', async () => {
    const user = userEvent.setup();
    render(<DatasetDetailRoute />);
    await user.click(screen.getByRole('tab', { name: 'Files' }));

    expect(screen.queryByTestId('dataset-files-tab-preview')).toBeNull();
    expect(screen.queryByTestId('mock-file-preview-content')).toBeNull();
  });
});
