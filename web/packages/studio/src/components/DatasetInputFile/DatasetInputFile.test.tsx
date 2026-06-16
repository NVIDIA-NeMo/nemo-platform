// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DEFAULT_WORKSPACE } from '@nemo/common/src/models/constants';
import { DatasetInputFile } from '@studio/components/DatasetInputFile';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { mockUseParams } from '@studio/tests/util/mockUseParams';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

// Holds the file content the mocked fetch should return for each test.
let currentTestFileContent = '';

// Mock the file-content fetch — returning a plain string from queryFn lets the
// real TestQueryClient.fetchQuery resolve with our test content.
vi.mock('@studio/api/datasets/useDatasetFileContent', () => ({
  datasetFileContentQueryOptions: (params: { workspace: string; name: string; path: string }) => ({
    queryKey: ['file-content', params.workspace, params.name, params.path],
    queryFn: async () => currentTestFileContent,
  }),
}));

// Mock UploadModal so the test can trigger a file submission directly without
// having to drive the full upload modal UI.
vi.mock('@nemo/common/src/components/UploadModal', () => ({
  UploadModal: ({
    open,
    onSubmit,
  }: {
    open: boolean;
    onSubmit: (data: {
      type: 'dataset';
      dataset: { workspace: string; name: string };
      path: string;
      url: string;
    }) => void | Promise<void>;
  }) => {
    if (!open) return null;
    return (
      <button
        data-testid="mock-upload-submit"
        onClick={() =>
          onSubmit({
            type: 'dataset',
            dataset: { workspace: 'default', name: 'test-dataset' },
            path: 'test-file.jsonl',
            url: 'fileset://default/test-dataset#test-file.jsonl',
          })
        }
      >
        Submit test file
      </button>
    );
  },
}));

const renderComponent = (props: Partial<React.ComponentProps<typeof DatasetInputFile>> = {}) => {
  return render(
    <TestProviders>
      <MemoryRouter initialEntries={[`/workspaces/${DEFAULT_WORKSPACE}`]}>
        <Routes>
          <Route
            path={`/workspaces/:${ROUTE_PARAMS.workspace}`}
            element={<DatasetInputFile onChange={vi.fn()} {...props} />}
          />
        </Routes>
      </MemoryRouter>
    </TestProviders>
  );
};

const selectFile = async (fileContent: string) => {
  currentTestFileContent = fileContent;
  const user = userEvent.setup();
  await user.click(await screen.findByRole('button', { name: 'Select File' }));
  await user.click(await screen.findByTestId('mock-upload-submit'));
};

describe('DatasetInputFile — file validation', () => {
  beforeEach(() => {
    mockUseParams({ [ROUTE_PARAMS.workspace]: DEFAULT_WORKSPACE });
  });

  afterEach(() => {
    currentTestFileContent = '';
  });

  it('shows an error when the file is neither valid JSON nor valid JSONL', async () => {
    renderComponent();
    await selectFile('this is not json or jsonl');

    expect(await screen.findByText(/File validation failed/i)).toBeInTheDocument();
    expect(screen.getByText(/Please ensure your file is valid JSON\/JSONL/i)).toBeInTheDocument();
  });

  it('shows "JSON is valid" for valid JSON content', async () => {
    renderComponent();
    await selectFile(JSON.stringify([{ foo: 'bar' }]));

    expect(await screen.findByText('JSON is valid')).toBeInTheDocument();
  });

  it('shows "JSONL is valid" for valid JSONL content', async () => {
    renderComponent();
    await selectFile('{"foo":"bar"}\n{"foo":"baz"}');

    expect(await screen.findByText('JSONL is valid')).toBeInTheDocument();
  });
});

describe('DatasetInputFile — schema detection', () => {
  beforeEach(() => {
    mockUseParams({ [ROUTE_PARAMS.workspace]: DEFAULT_WORKSPACE });
  });

  afterEach(() => {
    currentTestFileContent = '';
  });

  it('detects chat-completion schema when the file has a messages array', async () => {
    const jsonlRow = {
      messages: [
        { role: 'user', content: 'hello' },
        { role: 'assistant', content: 'hi there' },
      ],
    };
    renderComponent();
    await selectFile(JSON.stringify(jsonlRow));

    expect(await screen.findByText(/Detected Schema: chat-completion/i)).toBeInTheDocument();
  });

  it('detects completion schema when the file has prompt/completion keys', async () => {
    renderComponent();
    await selectFile(JSON.stringify({ prompt: 'Q?', completion: 'A!' }));

    expect(await screen.findByText(/Detected Schema: completion/i)).toBeInTheDocument();
  });

  it('shows manual mapping dropdowns when schema cannot be auto-detected', async () => {
    renderComponent();
    // Neither messages nor known prompt/completion keys
    await selectFile(JSON.stringify({ custom_field: 'x', custom_answer: 'y' }));

    expect(await screen.findByText(/Schema could not be auto-detected/i)).toBeInTheDocument();
    expect(await screen.findByText(/Map required keys from your input data/i)).toBeInTheDocument();
    // Both prompt + completion are required by default
    expect(screen.getByText('Prompt Key')).toBeInTheDocument();
    expect(screen.getByText('Completion Key')).toBeInTheDocument();
  });

  it('only shows dropdowns for keys that are required', async () => {
    renderComponent({ requirePromptKey: true, requireCompletionKey: false });
    await selectFile(JSON.stringify({ custom_field: 'x' }));

    await waitFor(() => {
      expect(screen.getByText('Prompt Key')).toBeInTheDocument();
    });
    // Completion key dropdown must not appear when not required
    expect(screen.queryByText('Completion Key')).not.toBeInTheDocument();
    expect(screen.queryByText('Ideal Response Key')).not.toBeInTheDocument();
  });
});
