// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FileSampleMethod } from '@nemo/common/src/utils/sampleTextLines';
import type { FilesetFileOutput } from '@nemo/sdk/generated/platform/schema';
import { DatasetSamplePanel } from '@studio/routes/FilesetDetailRoute/FilesetCard/DatasetSamplePanel';
import { render } from '@studio/tests/util/render';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

// Stub the snippet so the spec asserts on the props the panel feeds it
// (selected file + sampling method) without pulling in file-content fetching.
vi.mock('@studio/components/FileSamplingSnippet/FileSamplingSnippet', () => ({
  FileSamplingSnippet: ({
    filePath,
    sampleMethod,
    displayMode,
  }: {
    filePath: string;
    sampleMethod: FileSampleMethod;
    displayMode: string;
  }) => (
    <div
      data-testid="mock-snippet"
      data-file-path={filePath}
      data-sample-method={sampleMethod}
      data-display-mode={displayMode}
    />
  ),
}));

// Stub the method select as plain buttons so a click maps cleanly to onValueChange.
vi.mock('@studio/components/FileSamplingSnippet/FileSamplingMethodSelect', () => ({
  FileSamplingMethodSelect: ({
    onValueChange,
  }: {
    onValueChange: (m: FileSampleMethod) => void;
  }) => (
    <div data-testid="mock-method-select">
      {(['head', 'tail', 'random'] as const).map((m) => (
        <button key={m} type="button" onClick={() => onValueChange(m)}>
          {m}
        </button>
      ))}
    </div>
  ),
}));

const file = (path: string): FilesetFileOutput =>
  ({ path, file_ref: path, file_url: path, size: 1 }) as FilesetFileOutput;

const renderPanel = (files: FilesetFileOutput[] | undefined) =>
  render(<DatasetSamplePanel workspace="default" filesetName="ds" files={files} />);

describe('DatasetSamplePanel', () => {
  it('renders nothing when the fileset has no files', () => {
    renderPanel([]);
    expect(screen.queryByTestId('dataset-sample-panel')).toBeNull();
  });

  it('defaults to the first file (alphabetical) and head sampling', () => {
    renderPanel([file('train/b.jsonl'), file('train/a.jsonl')]);

    const snippet = screen.getByTestId('mock-snippet');
    expect(snippet).toHaveAttribute('data-file-path', 'train/a.jsonl');
    expect(snippet).toHaveAttribute('data-sample-method', 'head');
  });

  it('lists every file, regardless of extension (e.g. a README-only fileset)', () => {
    renderPanel([file('README.md')]);
    expect(screen.getByRole('combobox', { name: 'Sample file' })).toBeInTheDocument();
    expect(screen.getByTestId('mock-snippet')).toHaveAttribute('data-file-path', 'README.md');
  });

  it('uses table preview for JSONL/JSON and the code editor for other files', () => {
    const { rerender } = renderPanel([file('data.jsonl')]);
    expect(screen.getByTestId('mock-snippet')).toHaveAttribute('data-display-mode', 'table');

    rerender(
      <DatasetSamplePanel workspace="default" filesetName="ds" files={[file('notes.txt')]} />
    );
    expect(screen.getByTestId('mock-snippet')).toHaveAttribute('data-display-mode', 'code');
  });

  it('switches the previewed file when a different file is picked', async () => {
    const user = userEvent.setup();
    renderPanel([file('train/a.jsonl'), file('train/b.jsonl')]);

    expect(screen.getByTestId('mock-snippet')).toHaveAttribute('data-file-path', 'train/a.jsonl');

    await user.click(screen.getByRole('combobox', { name: 'Sample file' }));
    await user.click(await screen.findByRole('option', { name: 'train/b.jsonl' }));

    expect(screen.getByTestId('mock-snippet')).toHaveAttribute('data-file-path', 'train/b.jsonl');
  });

  it('forwards the selected sampling method to the snippet', async () => {
    const user = userEvent.setup();
    renderPanel([file('data.jsonl')]);

    await user.click(screen.getByRole('button', { name: 'tail' }));
    expect(screen.getByTestId('mock-snippet')).toHaveAttribute('data-sample-method', 'tail');

    await user.click(screen.getByRole('button', { name: 'random' }));
    expect(screen.getByTestId('mock-snippet')).toHaveAttribute('data-sample-method', 'random');
  });
});
