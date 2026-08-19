// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { TransformFileModal } from '@studio/components/FilesTable/TransformFileModal';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

let SOURCE_ROWS: Record<string, string>[] = [];

const withIdColumn = [
  { task_id: 'a1', category: 'billing', user_request: 'Where is my refund?', ideal_response: '..' },
];
const withoutIdColumn = [
  { category: 'billing', user_request: 'Where is my refund?', ideal_response: '..' },
];

const transformMock = vi.fn();
const onCloseMock = vi.fn();

vi.mock('@studio/hooks/useSelectedDatasetId', () => ({
  useSelectedDatasetId: () => 'default/test',
}));

vi.mock('@studio/api/datasets/useDatasetFileContent', () => ({
  useDatasetFileContent: () => ({
    data: SOURCE_ROWS.map((row) => JSON.stringify(row)).join('\n'),
    isLoading: false,
  }),
}));

vi.mock('@studio/api/datasets/useDatasetFileTransform', () => ({
  useDatasetFileTransform: () => ({ mutate: transformMock, isPending: false }),
}));

const renderModal = () =>
  render(
    <TestProviders>
      <TransformFileModal
        open
        onClose={onCloseMock}
        filepath="data.jsonl"
        datasetId="default/test"
      />
    </TestProviders>
  );

describe('TransformFileModal', () => {
  beforeEach(() => {
    transformMock.mockReset();
    onCloseMock.mockReset();
    SOURCE_ROWS = withIdColumn;
  });

  it('auto-maps the default format from the file columns', () => {
    renderModal();

    expect(
      screen.getByRole('combobox', { name: 'inputs.instruction source column' })
    ).toHaveTextContent('user_request');
  });

  it('transforms the file in place with the built template', async () => {
    const user = userEvent.setup();
    renderModal();

    await user.click(screen.getByRole('button', { name: 'Transform file' }));

    expect(transformMock).toHaveBeenCalledTimes(1);
    const { workspace, datasetName, filepath, template } = transformMock.mock.calls[0][0];
    expect({ workspace, datasetName, filepath }).toEqual({
      workspace: 'default',
      datasetName: 'test',
      filepath: 'data.jsonl',
    });
    expect(template).toMatchObject({
      id: '{{ task_id }}',
      intent: '{{ category }}',
      inputs: { instruction: '{{ user_request }}' },
    });
  });

  it('generates the identifier client-side when the file has no unique key', async () => {
    SOURCE_ROWS = withoutIdColumn;
    const user = userEvent.setup();
    renderModal();

    await user.click(screen.getByRole('button', { name: 'Transform file' }));

    expect(transformMock.mock.calls[0][0].generatedIdColumn).toBe('row_id');
  });

  it('blocks submission while a required field is unmapped', async () => {
    const user = userEvent.setup();
    renderModal();

    // Switching to Preference Pairs leaves `rejected` with no matching column.
    await user.click(screen.getByRole('radio', { name: 'Preference Pairs' }));

    expect(screen.getByText(/must have a source/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Transform file' })).toBeDisabled();
  });

  it('appends a fresh custom row once the last one is filled in', async () => {
    const user = userEvent.setup();
    renderModal();

    await user.click(screen.getByRole('radio', { name: 'Custom' }));

    // The four source columns pass through, leaving a fifth row blank.
    expect(screen.queryByLabelText('Output key 6')).not.toBeInTheDocument();

    await user.type(screen.getByLabelText('Output key 5'), 'summary');
    expect(screen.queryByLabelText('Output key 6')).not.toBeInTheDocument();

    await user.type(screen.getByLabelText('Template for key 5'), '{{{{ category }}');

    expect(screen.getByLabelText('Output key 6')).toHaveValue('');
    expect(screen.queryByRole('button', { name: 'Add key' })).not.toBeInTheDocument();
  });

  it('warns before discarding an edited mapping', async () => {
    const user = userEvent.setup();
    renderModal();

    await user.click(screen.getByRole('radio', { name: 'Custom' }));
    await user.type(screen.getByLabelText('Output key 1'), 'summary');
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.getByText('Discard this transform?')).toBeInTheDocument();
    expect(onCloseMock).not.toHaveBeenCalled();
  });
});
