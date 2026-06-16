// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { UploadModalProvider } from '@nemo/common/src/components/UploadModal/Context/UploadModalProvider';
import { useUploadModalContext } from '@nemo/common/src/components/UploadModal/Context/useUploadModalContext';
import { DatasetUploader } from '@nemo/common/src/components/UploadModal/DatasetUploader/index';
import { DatasetSelect } from '@nemo/common/src/components/UploadModal/DatasetUploader/Select';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock child components
vi.mock('@nemo/common/src/components/UploadModal/DatasetUploader/Select', () => ({
  DatasetSelect: vi.fn(),
}));

vi.mock('@nemo/common/src/components/UploadModal/DatasetUploader/NewDataset', () => ({
  NewDataset: () => <div>NewDataset Component</div>,
}));

vi.mock('@nemo/common/src/components/UploadModal/DatasetUploader/ExistingDataset', () => ({
  ExistingDataset: () => <div>ExistingDataset Component</div>,
}));

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <UploadModalProvider>{children}</UploadModalProvider>
    </QueryClientProvider>
  );
};

describe('DatasetUploader', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();

    // Set up the DatasetSelect mock implementation
    vi.mocked(DatasetSelect).mockImplementation(() => {
      const [, dispatch] = useUploadModalContext();

      return (
        <div>
          <button
            onClick={() =>
              dispatch({
                type: 'SET_DATASET',
                payload: {
                  type: 'existing',
                  dataset: {
                    id: 'default/existing',
                    name: 'existing',
                    workspace: 'default',
                    description: '',
                    purpose: 'dataset',
                    storage: { type: 'local', path: '/data' },
                    metadata: {},
                    custom_fields: {},
                    project: 'default',
                    created_at: '2024-01-01T00:00:00Z',
                    updated_at: '2024-01-01T00:00:00Z',
                  },
                },
              })
            }
          >
            Select Existing
          </button>
          <button
            onClick={() => dispatch({ type: 'SET_DATASET', payload: { type: 'new', name: '' } })}
          >
            Select New Fileset
          </button>
        </div>
      );
    });
  });

  it('renders dataset select', () => {
    render(<DatasetUploader projectId="test-project" />, { wrapper: createWrapper() });

    expect(screen.getByText('Select Existing')).toBeInTheDocument();
    expect(screen.getByText('Select New Fileset')).toBeInTheDocument();
  });

  it('shows NewDataset component when new dataset is selected', async () => {
    render(<DatasetUploader projectId="test-project" />, { wrapper: createWrapper() });

    // Click to select new dataset
    await user.click(screen.getByText('Select New Fileset'));

    expect(screen.getByText('NewDataset Component')).toBeInTheDocument();
  });

  it('shows ExistingDataset component when existing dataset is selected', async () => {
    render(<DatasetUploader projectId="test-project" />, { wrapper: createWrapper() });

    // Click to select existing dataset
    await user.click(screen.getByText('Select Existing'));

    expect(screen.getByText('ExistingDataset Component')).toBeInTheDocument();
  });

  it('switches between new and existing dataset views', async () => {
    render(<DatasetUploader projectId="test-project" />, { wrapper: createWrapper() });

    // Initially no dataset selected
    expect(screen.queryByText('NewDataset Component')).not.toBeInTheDocument();
    expect(screen.queryByText('ExistingDataset Component')).not.toBeInTheDocument();

    // Select new dataset
    await user.click(screen.getByText('Select New Fileset'));
    expect(screen.getByText('NewDataset Component')).toBeInTheDocument();

    // Switch to existing dataset
    await user.click(screen.getByText('Select Existing'));
    expect(screen.getByText('ExistingDataset Component')).toBeInTheDocument();
    expect(screen.queryByText('NewDataset Component')).not.toBeInTheDocument();
  });
});
