// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FileValidationPanel } from '@studio/components/sidePanels/MetricRunSidePanel/FileValidationPanel';
import { TestProviders } from '@studio/tests/util/TestProviders';
import { render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';

let currentTestFileContent = '';

vi.mock('@studio/api/datasets/useDatasetFileContent', () => ({
  datasetFileContentQueryOptions: (params: { workspace: string; name: string; path: string }) => ({
    queryKey: ['metric-run-file-content', params.workspace, params.name, params.path],
    queryFn: async () => currentTestFileContent,
  }),
}));

const renderPanel = (props: Partial<ComponentProps<typeof FileValidationPanel>> = {}) => {
  return render(
    <TestProviders>
      <FileValidationPanel
        dataset="default/test-dataset#data.jsonl"
        jobType="online"
        promptTemplate="{{item.prompt}}"
        workspace="default"
        {...props}
      />
    </TestProviders>
  );
};

describe('Metric run FileValidationPanel', () => {
  afterEach(() => {
    currentTestFileContent = '';
  });

  it('does not render when no dataset is selected', () => {
    renderPanel({ dataset: null });

    expect(screen.queryByText('File Validation')).not.toBeInTheDocument();
  });

  it('renders validation details after loading a selected dataset file', async () => {
    currentTestFileContent = '{"prompt":"hello","completion":"hi"}';
    renderPanel();

    expect(await screen.findByText('File Validation')).toBeInTheDocument();
    expect(screen.getByText('JSONL is valid')).toBeInTheDocument();
    expect(screen.getByText('Detected Schema: completion')).toBeInTheDocument();
    expect(screen.getByText('All prompt template fields detected')).toBeInTheDocument();
  });

  it('shows missing prompt template fields', async () => {
    currentTestFileContent = '{"prompt":"hello","completion":"hi"}';
    renderPanel({ promptTemplate: '{{item.prompt}} {{item.context}}' });

    expect(
      await screen.findByText('Prompt template fields missing from dataset: context')
    ).toBeInTheDocument();
  });

  it('validates empty file content instead of treating it as missing data', async () => {
    currentTestFileContent = '';
    renderPanel();

    expect(await screen.findByText(/^File validation failed:/)).toBeInTheDocument();
  });

  it('emits variable options from the selected dataset schema', async () => {
    const onVariablesChange = vi.fn();
    currentTestFileContent = '{"prompt":"hello","completion":"hi"}';
    renderPanel({ onVariablesChange });

    expect(await screen.findByText('File Validation')).toBeInTheDocument();
    expect(onVariablesChange).toHaveBeenLastCalledWith([
      { name: 'prompt', description: 'Dataset field' },
      { name: 'completion', description: 'Dataset field' },
    ]);
  });
});
