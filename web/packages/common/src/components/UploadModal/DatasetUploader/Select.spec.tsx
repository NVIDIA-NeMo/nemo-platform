// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { UploadModalProvider } from '@nemo/common/src/components/UploadModal/Context/UploadModalProvider';
import { useUploadModalContext } from '@nemo/common/src/components/UploadModal/Context/useUploadModalContext';
import { UploadModalState } from '@nemo/common/src/components/UploadModal/Context/useUploadModalReducer';
import { DatasetSelect } from '@nemo/common/src/components/UploadModal/DatasetUploader/Select';
import { filesListFilesetFiles, useFilesListFilesets } from '@nemo/sdk/generated/platform/api';
import { FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Mock the SDK hooks
vi.mock('@nemo/sdk/generated/platform/api', () => ({
  useFilesListFilesets: vi.fn(),
  filesListFilesetFiles: vi.fn(),
}));

const mockFilesets: FilesetOutput[] = [
  {
    id: 'default/dataset1',
    name: 'dataset1',
    workspace: 'default',
    description: '',
    purpose: 'dataset',
    storage: { type: 'local', path: '/data' } as const,
    metadata: {},
    custom_fields: {},
    project: 'default',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'default/dataset2',
    name: 'dataset2',
    workspace: 'default',
    description: '',
    purpose: 'dataset',
    storage: { type: 'local', path: '/data' } as const,
    metadata: {},
    custom_fields: {},
    project: 'default',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
  },
];

// Helper component to access context in tests
const ContextReader = ({
  onContextChange,
}: {
  onContextChange: (state: UploadModalState) => void;
}) => {
  const [state] = useUploadModalContext();
  onContextChange(state);
  return null;
};

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

describe('DatasetSelect', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useFilesListFilesets).mockReturnValue({
      data: { data: mockFilesets },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useFilesListFilesets>);
    vi.mocked(filesListFilesetFiles).mockResolvedValue({ data: [] });
  });

  it('renders dataset select with datasets', () => {
    render(<DatasetSelect project="test-project" />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByRole('combobox')).toBeInTheDocument();
  });

  it('queries filesets with purpose filter set to dataset', () => {
    render(<DatasetSelect project="test-project" />, {
      wrapper: createWrapper(),
    });

    expect(useFilesListFilesets).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        filter: { purpose: 'dataset' },
      })
    );
  });

  it('shows loading state', async () => {
    vi.mocked(useFilesListFilesets).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as ReturnType<typeof useFilesListFilesets>);

    render(<DatasetSelect project="test-project" />, {
      wrapper: createWrapper(),
    });

    const select = screen.getByRole('combobox');
    expect(select).toBeInTheDocument();

    // Open the dropdown to see the loading state
    await user.click(select);
    expect(screen.getByText('Loading datasets...')).toBeInTheDocument();
  });

  it('shows error state', async () => {
    vi.mocked(useFilesListFilesets).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as ReturnType<typeof useFilesListFilesets>);

    render(<DatasetSelect project="test-project" />, {
      wrapper: createWrapper(),
    });

    const select = screen.getByRole('combobox');
    expect(select).toBeInTheDocument();

    // Open the dropdown to see the error state
    await user.click(select);
    expect(screen.getByText('Error loading datasets...')).toBeInTheDocument();
  });

  it('updates context when dataset is selected', async () => {
    let contextState: UploadModalState | undefined;

    render(
      <>
        <DatasetSelect project="test-project" />
        <ContextReader onContextChange={(state) => (contextState = state)} />
      </>,
      {
        wrapper: createWrapper(),
      }
    );

    const select = screen.getByRole('combobox');
    await user.click(select);

    await waitFor(() => {
      const options = screen.getAllByRole('option');
      // Filter to only enabled options (the dataset options, not loading/error)
      const enabledOptions = options.filter(
        (option) =>
          !option.hasAttribute('aria-disabled') || option.getAttribute('aria-disabled') === 'false'
      );
      expect(enabledOptions.length).toBeGreaterThan(0);
    });

    // Find the first enabled dataset option (not "New Dataset" which is at the end)
    const datasetOption = screen.getByRole('option', { name: 'dataset1' });
    await user.click(datasetOption);

    await waitFor(() => {
      expect(contextState?.dataset).toBeDefined();
    });

    expect(contextState?.dataset?.type).toBe('existing');
    expect(contextState?.dataset?.type === 'existing' && contextState.dataset.dataset.name).toBe(
      'dataset1'
    );
  });

  it('includes "New Dataset" option', async () => {
    render(<DatasetSelect project="test-project" />, {
      wrapper: createWrapper(),
    });

    const select = screen.getByRole('combobox');
    await user.click(select);

    expect(await screen.findByText('New Dataset')).toBeInTheDocument();
  });

  it('updates context with new dataset type when New Dataset is selected', async () => {
    let contextState: UploadModalState | undefined;

    render(
      <>
        <DatasetSelect project="test-project" />
        <ContextReader onContextChange={(state) => (contextState = state)} />
      </>,
      {
        wrapper: createWrapper(),
      }
    );

    const select = screen.getByRole('combobox');
    await user.click(select);

    expect(await screen.findByText('New Dataset')).toBeInTheDocument();

    await user.click(screen.getByText('New Dataset'));

    await waitFor(() => {
      expect(contextState?.dataset).toBeDefined();
    });

    expect(contextState?.dataset?.type).toBe('new');
    expect(contextState?.dataset?.type === 'new' && contextState.dataset.name).toBe('');
  });

  it('can be disabled', async () => {
    render(<DatasetSelect project="test-project" disabled />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      const select = screen.getByRole('combobox');
      expect(select).toBeDisabled();
    });
  });
});
