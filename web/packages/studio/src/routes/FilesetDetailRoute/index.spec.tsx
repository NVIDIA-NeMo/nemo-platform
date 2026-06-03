// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FilesetPurpose, type FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { FilesetDetailRoute } from '@studio/routes/FilesetDetailRoute';
import { renderRoute, screen } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

const { mockRetrieveFileset, mockListFiles } = vi.hoisted(() => ({
  mockRetrieveFileset: vi.fn(),
  mockListFiles: vi.fn(),
}));

const externalFileset: FilesetOutput = {
  id: 'default/test-fileset',
  name: 'test-fileset',
  workspace: 'default',
  description: '',
  purpose: FilesetPurpose.dataset,
  storage: { type: 'huggingface', repo_id: 'nvidia/test-fileset' } as FilesetOutput['storage'],
  metadata: {},
  custom_fields: {},
  project: '',
  created_at: '',
  updated_at: '',
};

vi.mock('@nemo/sdk/generated/platform/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@nemo/sdk/generated/platform/api')>();
  return {
    ...actual,
    useFilesRetrieveFileset: mockRetrieveFileset,
    useFilesListFilesetFiles: mockListFiles,
  };
});

// The Card and Files content have their own specs; stub them so this spec
// focuses on the route's tab routing and data plumbing.
vi.mock('@studio/components/FilesetCard', () => ({
  FilesetCard: ({
    testId,
    isFilesLoading,
    isFilesError,
  }: {
    testId?: string;
    isFilesLoading?: boolean;
    isFilesError?: boolean;
  }) => (
    <div
      data-testid={testId}
      data-loading={String(isFilesLoading)}
      data-error={String(isFilesError)}
    >
      Fileset Card
    </div>
  ),
}));

vi.mock('@studio/routes/FilesetDetailRoute/FilesTab', () => ({
  FilesTab: () => <div data-testid="fileset-files-tab">Files Tab</div>,
}));

vi.mock('@studio/hooks/useWorkspaceFromPath', () => ({
  useWorkspaceFromPath: () => 'default',
}));

vi.mock('@studio/util/hooks/useRequiredPathParams', () => ({
  useRequiredPathParams: () => ({ filesetId: 'default%2Ftest-fileset' }),
}));

describe('FilesetDetailRoute', () => {
  beforeEach(() => {
    mockRetrieveFileset.mockReturnValue({
      data: externalFileset,
      isPending: false,
      isError: false,
    });
    mockListFiles.mockReturnValue({
      data: { data: [] },
      isPending: false,
      isFetching: false,
      isError: false,
    });
  });

  it('renders the Card tab by default with the fileset name', () => {
    renderRoute(<FilesetDetailRoute />);

    expect(screen.getByTestId('nv-page-header-heading')).toHaveTextContent('test-fileset');
    expect(screen.getByRole('tab', { name: 'Dataset Card' })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    expect(screen.getByTestId('fileset-detail-card')).toBeInTheDocument();
    expect(screen.queryByTestId('fileset-files-tab')).not.toBeInTheDocument();
  });

  it('switches to the Files tab when the Files tab is clicked', async () => {
    const user = userEvent.setup();
    renderRoute(<FilesetDetailRoute />);

    await user.click(screen.getByRole('tab', { name: 'Files' }));

    expect(screen.getByTestId('fileset-files-tab')).toBeInTheDocument();
    expect(screen.queryByTestId('fileset-detail-card')).not.toBeInTheDocument();
  });

  it('opens the Files tab when the initial URL has ?tab=files', () => {
    renderRoute(<FilesetDetailRoute />, { history: '/?tab=files' });

    expect(screen.getByTestId('fileset-files-tab')).toBeInTheDocument();
  });

  it('falls back to the Card tab when ?tab= is an unknown value', () => {
    renderRoute(<FilesetDetailRoute />, { history: '/?tab=garbage' });

    expect(screen.getByTestId('fileset-detail-card')).toBeInTheDocument();
    expect(screen.queryByTestId('fileset-files-tab')).not.toBeInTheDocument();
  });

  it('forwards a loading state to the fileset card while the record is loading', () => {
    mockRetrieveFileset.mockReturnValue({ data: undefined, isPending: true, isError: false });
    renderRoute(<FilesetDetailRoute />);

    expect(screen.getByTestId('fileset-detail-card')).toHaveAttribute('data-loading', 'true');
  });

  it('forwards an error state to the fileset card when the record fails to load', () => {
    mockRetrieveFileset.mockReturnValue({ data: undefined, isPending: false, isError: true });
    renderRoute(<FilesetDetailRoute />);

    expect(screen.getByTestId('fileset-detail-card')).toHaveAttribute('data-error', 'true');
  });

  it('labels the Card tab "Model Card" for model filesets', () => {
    mockRetrieveFileset.mockReturnValue({
      data: { ...externalFileset, purpose: FilesetPurpose.model },
      isPending: false,
      isError: false,
    });
    renderRoute(<FilesetDetailRoute />);

    expect(screen.getByRole('tab', { name: 'Model Card' })).toBeInTheDocument();
  });
});
