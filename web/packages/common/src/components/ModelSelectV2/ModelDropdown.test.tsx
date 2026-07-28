// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelWorkspaceGroup } from '@nemo/common/src/api/models/useModels';
import { ModelDropdown } from '@nemo/common/src/components/ModelSelectV2/ModelDropdown';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

const makeModel = (name: string, workspace = 'nvidia'): ModelEntity =>
  ({ id: name, name, workspace }) as unknown as ModelEntity;

const groups: ModelWorkspaceGroup[] = [
  { workspace: 'nvidia', models: [makeModel('nemotron-8b'), makeModel('llama-3.1-8b')] },
];

type Props = React.ComponentProps<typeof ModelDropdown>;

const renderOpen = (props: Partial<Props> = {}) =>
  render(
    <ModelDropdown
      open
      onOpenChange={vi.fn()}
      value={null}
      onValueChange={vi.fn()}
      groups={groups}
      {...props}
    />
  );

const typeFilter = (text: string) =>
  fireEvent.change(screen.getByTestId('model-select-v2-filter'), { target: { value: text } });

/** Names of the rows in the list, ignoring the details panel each row also renders. */
const listedModels = () =>
  screen.queryAllByTestId('model-dropdown-item').map((item) => item.textContent);

describe('ModelDropdown', () => {
  describe('search', () => {
    it('filters the given groups itself when no onSearchChange is provided', async () => {
      renderOpen();
      await waitFor(() => expect(listedModels()).toHaveLength(2));

      typeFilter('llama');

      await waitFor(() => expect(listedModels()).toEqual(['llama-3.1-8b']));
    });

    it('reports the debounced term and leaves the groups alone when onSearchChange is provided', async () => {
      const onSearchChange = vi.fn();
      renderOpen({ onSearchChange, searchDebounceMs: 0 });

      typeFilter('llama');

      await waitFor(() => expect(onSearchChange).toHaveBeenCalledWith('llama'));
      // The caller owns the query, so both models stay listed until new groups arrive.
      expect(listedModels()).toEqual(['nemotron-8b', 'llama-3.1-8b']);
    });
  });

  describe('paging', () => {
    it('asks for the next page while more remain', async () => {
      const onLoadMore = vi.fn();
      renderOpen({ onLoadMore, hasMore: true });

      await waitFor(() => expect(onLoadMore).toHaveBeenCalled());
    });

    it('does not ask for more once the last page has loaded', async () => {
      const onLoadMore = vi.fn();
      renderOpen({ onLoadMore, hasMore: false });

      await waitFor(() => expect(listedModels()).toHaveLength(2));
      expect(onLoadMore).not.toHaveBeenCalled();
    });

    it('shows the done message only after the last page', async () => {
      const { rerender } = renderOpen({
        onLoadMore: vi.fn(),
        hasMore: true,
        doneLoadingMessage: 'No more models',
      });
      await waitFor(() => expect(listedModels()).toHaveLength(2));
      expect(screen.queryByText('No more models')).not.toBeInTheDocument();

      rerender(
        <ModelDropdown
          open
          onOpenChange={vi.fn()}
          value={null}
          onValueChange={vi.fn()}
          groups={groups}
          onLoadMore={vi.fn()}
          hasMore={false}
          doneLoadingMessage="No more models"
        />
      );

      expect(await screen.findByText('No more models')).toBeInTheDocument();
    });
  });

  describe('trigger', () => {
    it('falls back to the name in the URN when the selection is not in the loaded pages', () => {
      renderOpen({ open: false, value: { model: 'nvidia/not-yet-loaded' }, groups: [] });

      expect(screen.getByTestId('model-select-v2-trigger')).toHaveTextContent('not-yet-loaded');
    });

    it('prefers the entity the selection carries', () => {
      renderOpen({
        open: false,
        value: { model: 'nvidia/nemotron-8b', entity: makeModel('nemotron-8b') },
        groups: [],
      });

      expect(screen.getByTestId('model-select-v2-trigger')).toHaveTextContent('nemotron-8b');
    });
  });
});
