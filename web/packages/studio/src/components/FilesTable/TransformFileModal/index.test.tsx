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
// No column an assistant turn could be guessed from.
const withoutResponseColumn = [{ task_id: 'a1', user_request: 'Where is my refund?' }];

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

let transformOptions: { onError?: (error: Error) => void } = {};

vi.mock('@studio/api/datasets/useDatasetFileTransform', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@studio/api/datasets/useDatasetFileTransform')>();
  return {
    ...actual,
    useDatasetFileTransform: (options: { onError?: (error: Error) => void }) => {
      transformOptions = options;
      return { mutate: transformMock, isPending: false };
    },
  };
});

const renderModal = (filepath = 'data.jsonl') =>
  render(
    <TestProviders>
      <TransformFileModal open onClose={onCloseMock} filepath={filepath} datasetId="default/test" />
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
    SOURCE_ROWS = withoutResponseColumn;
    const user = userEvent.setup();
    renderModal();

    // Messages needs an assistant turn, which nothing in this file matches.
    await user.click(screen.getByRole('radio', { name: 'Messages' }));

    expect(
      await screen.findByText(/must have a source before this transform can run/)
    ).toBeInTheDocument();
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

  it('blocks a file that is not JSONL, since the transform rewrites it as JSONL', () => {
    // The mocked content is JSONL, so parsing it as CSV logs.
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderModal('data.csv');

    expect(screen.getByText(/only .jsonl files can be transformed in place/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Transform file' })).toBeDisabled();
    error.mockRestore();
  });

  it('surfaces a failed transform and leaves the modal open to retry', async () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderModal();

    transformOptions.onError?.(new Error('Only JSONL files can be transformed in place.'));

    expect(
      await screen.findByText('Only JSONL files can be transformed in place.')
    ).toBeInTheDocument();
    expect(onCloseMock).not.toHaveBeenCalled();
    error.mockRestore();
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
