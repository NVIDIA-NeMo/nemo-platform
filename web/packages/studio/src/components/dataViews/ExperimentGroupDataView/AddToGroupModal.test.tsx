// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { MockToastProvider } from '@nemo/common/src/tests/MockToastProvider';
import type { ExperimentGroupResponse } from '@nemo/sdk/generated/platform/schema';
import { AddToGroupModal } from '@studio/components/dataViews/ExperimentGroupDataView/AddToGroupModal';
import type { EvaluationRow } from '@studio/components/dataViews/ExperimentGroupDataView/useExperimentGroupEvaluations';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Hoisted mocks for the SDK hooks the modal calls.
const { mockMutate, mockUseListExperimentGroups } = vi.hoisted(() => ({
  mockMutate: vi.fn<(...args: unknown[]) => void>(),
  mockUseListExperimentGroups: vi.fn<() => { data: unknown; isLoading: boolean }>(),
}));

vi.mock('@nemo/sdk/generated/platform/api', async () => {
  const actual = await vi.importActual<typeof import('@nemo/sdk/generated/platform/api')>(
    '@nemo/sdk/generated/platform/api'
  );
  return {
    ...actual,
    useListExperimentGroups: () => mockUseListExperimentGroups(),
    useAddEvaluationToGroup: () => ({ mutate: mockMutate, isPending: false }),
  };
});

const makeGroup = (id: string, name: string): ExperimentGroupResponse => ({
  id,
  name,
  workspace: 'default',
  default_sort: '-created_at',
  experiment_count: 0,
});

const GROUPS: ExperimentGroupResponse[] = [
  makeGroup('g1', 'Alpha benchmarks'),
  makeGroup('g2', 'Beta benchmarks'),
  makeGroup('g3', 'Gamma benchmarks'),
];

// The evaluation already belongs to g1, so g1 must be excluded from the picker.
const EVALUATION = {
  id: 'eval-1',
  name: 'eval-1',
  experiment_ids: ['g1'],
} as unknown as EvaluationRow;

function makeWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <MockToastProvider>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </MockToastProvider>
  );
}

function renderModal() {
  const Wrapper = makeWrapper();
  return render(
    <Wrapper>
      <AddToGroupModal
        open
        onClose={vi.fn()}
        workspace="default"
        evaluation={EVALUATION}
        currentExperimentGroupId="current-group"
      />
    </Wrapper>
  );
}

describe('AddToGroupModal', () => {
  beforeEach(() => {
    mockMutate.mockReset();
    mockUseListExperimentGroups.mockReset();
    mockUseListExperimentGroups.mockReturnValue({
      data: { data: GROUPS },
      isLoading: false,
    });
  });

  it('lists selectable groups, excluding groups the evaluation already belongs to', () => {
    renderModal();
    // g2 and g3 are offered; g1 (already a member) is not.
    expect(screen.getByRole('option', { name: 'Beta benchmarks' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Gamma benchmarks' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Alpha benchmarks' })).not.toBeInTheDocument();
  });

  it('filters the list by the search text (case-insensitive)', async () => {
    const user = userEvent.setup();
    renderModal();
    await user.type(screen.getByRole('textbox', { name: /search groups/i }), 'gamma');
    expect(screen.getByRole('option', { name: 'Gamma benchmarks' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Beta benchmarks' })).not.toBeInTheDocument();
  });

  it('calls the add hook with the evaluation name and selected group id on select', async () => {
    const user = userEvent.setup();
    renderModal();
    await user.click(screen.getByRole('option', { name: 'Beta benchmarks' }));
    expect(mockMutate).toHaveBeenCalledTimes(1);
    expect(mockMutate).toHaveBeenCalledWith(
      { workspace: 'default', name: 'eval-1', groupId: 'g2' },
      expect.objectContaining({
        onSuccess: expect.any(Function),
        onError: expect.any(Function),
      })
    );
  });

  it('shows an empty message when every group is already a member', () => {
    mockUseListExperimentGroups.mockReturnValue({
      data: { data: [makeGroup('g1', 'Alpha benchmarks')] },
      isLoading: false,
    });
    renderModal();
    expect(screen.getByText('No groups found.')).toBeInTheDocument();
    expect(screen.queryByRole('option')).not.toBeInTheDocument();
  });
});
