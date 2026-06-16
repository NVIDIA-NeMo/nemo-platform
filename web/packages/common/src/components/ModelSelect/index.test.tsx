// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import { ModelSelect } from '@nemo/common/src/components/ModelSelect';
import { DEFAULT_NAMESPACE } from '@nemo/common/src/constants';
import { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useForm } from 'react-hook-form';

// Mock data
const mockModels: ModelEntity[] = [
  {
    id: 'model-1',
    name: 'Model 1',
    workspace: DEFAULT_NAMESPACE,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 'model-2',
    name: 'Model 2',
    workspace: DEFAULT_NAMESPACE,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
  {
    id: 'model-3',
    name: 'Model 3',
    workspace: DEFAULT_NAMESPACE,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-01T00:00:00Z',
  },
];

const mockOnChange = vi.fn();
const mockOnBlur = vi.fn();

describe('ModelSelect', () => {
  const user = userEvent.setup();
  const renderAndOpen = async ({ models }: { models?: ModelEntity[] | null } = {}) => {
    const { result } = renderHook(() => useForm());
    render(
      <ModelSelect
        models={models === null ? undefined : (models ?? mockModels)}
        onChange={mockOnChange}
        onBlur={mockOnBlur}
        useControllerProps={{
          name: 'model',
          control: result.current.control,
        }}
      />
    );
    const input = screen.getByRole('combobox');
    await user.click(input);
  };
  it('renders option list with models', async () => {
    await renderAndOpen();
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(mockModels.length);
  });

  it('filters models', async () => {
    await renderAndOpen();
    const input = screen.getByPlaceholderText('Filter');
    await user.type(input, 'Model 1');
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent('Model 1');
  });

  it('calls onChange/onBlur', async () => {
    await renderAndOpen();
    const options = screen.getAllByRole('option');
    const option = options[0];
    await user.click(option);
    await user.tab();
    expect(mockOnChange).toHaveBeenCalledTimes(1);
    expect(mockOnChange).toBeCalledWith('default/Model 1');
    expect(mockOnBlur).toHaveBeenCalled();
  });

  it('renders No Models Found option when no models provided', async () => {
    await renderAndOpen({ models: [] });
    const listbox = screen.queryByRole('option');
    expect(listbox).not.toBeInTheDocument();
    expect(screen.getByText('No Models Found')).toBeInTheDocument();
  });

  it('renders "Loading Models..." when loading is true', async () => {
    const { result } = renderHook(() => useForm());
    render(
      <ModelSelect
        models={mockModels}
        onChange={mockOnChange}
        onBlur={mockOnBlur}
        useControllerProps={{
          name: 'model',
          control: result.current.control,
        }}
        loading
      />
    );
    const input = screen.getByRole('combobox');
    expect(input).toHaveTextContent('Loading Models...');
  });

  describe('Workspace groups rendering', () => {
    const mockGroups: ModelWorkspaceGroup[] = [
      {
        workspace: 'my-workspace',
        models: [
          {
            id: 'model-ft',
            name: 'Fine-Tuned Model',
            workspace: 'my-workspace',
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-01-01T00:00:00Z',
          },
        ],
      },
      {
        workspace: DEFAULT_NAMESPACE,
        models: [
          {
            id: 'model-a',
            name: 'Base Model A',
            workspace: DEFAULT_NAMESPACE,
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-01-01T00:00:00Z',
          },
          {
            id: 'model-b',
            name: 'Base Model B',
            workspace: DEFAULT_NAMESPACE,
            created_at: '2025-01-01T00:00:00Z',
            updated_at: '2025-01-01T00:00:00Z',
          },
        ],
      },
    ];

    const renderGroupedAndOpen = async (groups: ModelWorkspaceGroup[]) => {
      const { result } = renderHook(() => useForm());
      render(
        <ModelSelect
          groups={groups}
          onChange={mockOnChange}
          onBlur={mockOnBlur}
          useControllerProps={{
            name: 'model',
            control: result.current.control,
          }}
        />
      );
      const input = screen.getByRole('combobox');
      await user.click(input);
    };

    it('renders workspace headings and models from groups', async () => {
      await renderGroupedAndOpen(mockGroups);
      expect(screen.getByText('my-workspace')).toBeInTheDocument();
      expect(screen.getByText(DEFAULT_NAMESPACE)).toBeInTheDocument();
      const options = screen.getAllByRole('option');
      expect(options).toHaveLength(3);
      expect(options[0]).toHaveTextContent('Fine-Tuned Model');
      expect(options[1]).toHaveTextContent('Base Model A');
      expect(options[2]).toHaveTextContent('Base Model B');
    });

    it('renders No Models Found when groups are empty', async () => {
      await renderGroupedAndOpen([]);
      expect(screen.queryByRole('option')).not.toBeInTheDocument();
      expect(screen.getByText('No Models Found')).toBeInTheDocument();
    });

    it('renders No Models Found when all groups have empty models', async () => {
      await renderGroupedAndOpen([{ workspace: 'empty-ws', models: [] }]);
      expect(screen.queryByRole('option')).not.toBeInTheDocument();
      expect(screen.getByText('No Models Found')).toBeInTheDocument();
    });

    it('calls onChange with model URN when a grouped model is selected', async () => {
      await renderGroupedAndOpen(mockGroups);
      const options = screen.getAllByRole('option');
      await user.click(options[0]);
      expect(mockOnChange).toHaveBeenCalledWith('my-workspace/Fine-Tuned Model');
    });
  });

  describe('Server-driven search and infinite scroll', () => {
    let mockObserverCallback: ((entries: IntersectionObserverEntry[]) => void) | null = null;
    const IntersectionObserverMock = vi.fn(function IntersectionObserverMock(
      callback: (entries: IntersectionObserverEntry[]) => void
    ) {
      mockObserverCallback = callback;
      return {
        observe: vi.fn(),
        unobserve: vi.fn(),
        disconnect: vi.fn(),
      };
    });

    beforeAll(() => {
      vi.stubGlobal('IntersectionObserver', IntersectionObserverMock);
    });

    afterEach(() => {
      mockObserverCallback = null;
    });

    afterAll(() => {
      vi.unstubAllGlobals();
    });

    it('calls onSearchChange with debounced value when user types in search input', async () => {
      const onSearchChange = vi.fn();
      const { result } = renderHook(() => useForm());
      render(
        <ModelSelect
          models={mockModels}
          onSearchChange={onSearchChange}
          useControllerProps={{ name: 'model', control: result.current.control }}
          searchDebounceMs={100}
        />
      );
      await user.click(screen.getByRole('combobox'));
      const searchInput = await screen.findByPlaceholderText('Search...');
      await user.type(searchInput, 'foo');

      await waitFor(() => {
        expect(onSearchChange).toHaveBeenCalledWith('foo');
      });
    });

    it('shows Search... placeholder when onSearchChange is provided', async () => {
      const onSearchChange = vi.fn();
      const { result } = renderHook(() => useForm());
      render(
        <ModelSelect
          models={mockModels}
          onSearchChange={onSearchChange}
          useControllerProps={{ name: 'model', control: result.current.control }}
        />
      );
      await user.click(screen.getByRole('combobox'));
      expect(await screen.findByPlaceholderText('Search...')).toBeInTheDocument();
    });

    it('calls onLoadMore when loader sentinel becomes visible', async () => {
      const onLoadMore = vi.fn().mockResolvedValue(undefined);
      const { result } = renderHook(() => useForm());
      render(
        <ModelSelect
          models={mockModels}
          onLoadMore={onLoadMore}
          hasMore
          useControllerProps={{ name: 'model', control: result.current.control }}
        />
      );
      await user.click(screen.getByRole('combobox'));
      await waitFor(() => {
        expect(mockObserverCallback).not.toBeNull();
      });
      await act(async () => {
        mockObserverCallback!([{ isIntersecting: true } as IntersectionObserverEntry]);
      });
      await waitFor(() => {
        expect(onLoadMore).toHaveBeenCalledTimes(1);
      });
    });

    it('does not call onLoadMore when hasMore is false', async () => {
      const onLoadMore = vi.fn().mockResolvedValue(undefined);
      const { result } = renderHook(() => useForm());
      render(
        <ModelSelect
          models={mockModels}
          onLoadMore={onLoadMore}
          hasMore={false}
          useControllerProps={{ name: 'model', control: result.current.control }}
        />
      );
      await user.click(screen.getByRole('combobox'));
      await waitFor(() => {
        expect(mockObserverCallback).not.toBeNull();
      });
      await act(async () => {
        mockObserverCallback!([{ isIntersecting: true } as IntersectionObserverEntry]);
      });
      expect(onLoadMore).not.toHaveBeenCalled();
    });

    it('shows default doneLoadingMessage when all pages loaded', async () => {
      const { result } = renderHook(() => useForm());
      render(
        <ModelSelect
          models={mockModels}
          onLoadMore={vi.fn()}
          hasMore={false}
          useControllerProps={{ name: 'model', control: result.current.control }}
        />
      );
      await user.click(screen.getByRole('combobox'));
      expect(await screen.findByText('All models loaded')).toBeInTheDocument();
    });

    it('shows custom doneLoadingMessage when provided', async () => {
      const { result } = renderHook(() => useForm());
      render(
        <ModelSelect
          models={mockModels}
          onLoadMore={vi.fn()}
          hasMore={false}
          doneLoadingMessage="No more models to load"
          useControllerProps={{ name: 'model', control: result.current.control }}
        />
      );
      await user.click(screen.getByRole('combobox'));
      expect(await screen.findByText('No more models to load')).toBeInTheDocument();
    });

    it('shows loading spinner at bottom when isLoadingMore is true', async () => {
      const { result } = renderHook(() => useForm());
      render(
        <ModelSelect
          models={mockModels}
          onLoadMore={vi.fn()}
          hasMore
          isLoadingMore
          useControllerProps={{ name: 'model', control: result.current.control }}
        />
      );
      await user.click(screen.getByRole('combobox'));
      expect(await screen.findByLabelText('Loading more models')).toBeInTheDocument();
    });
  });
});
