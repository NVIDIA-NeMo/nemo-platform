// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { FileListItem } from '@nemo/common/src/components/FileList';
import { FilesetFileBlockingInput } from '@studio/components/agents/AgentBlockingInput/FilesetFileBlockingInput';
import type { AgentBlockingInputSubmission } from '@studio/components/agents/AgentBlockingInput/types';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

let capturedOnFileSelected: ((file: FileListItem | null) => void) | null = null;

vi.mock('@nemo/common/src/components/DatasetFileSelect/ControlledDatasetFileSelect', () => ({
  ControlledDatasetFileSelect: vi.fn(
    (props: { onFileSelected?: (file: FileListItem | null) => void }) => {
      capturedOnFileSelected = props.onFileSelected ?? null;
      return <div data-testid="controlled-dataset-file-select" />;
    }
  ),
}));

vi.mock('@studio/components/agents/AgentBlockingInput/AgentBlockingInputFrame', () => ({
  AgentBlockingInputFrame: vi.fn(
    ({
      children,
      onSubmit,
      submitDisabled,
    }: {
      children: React.ReactNode;
      onSubmit: () => void;
      submitDisabled?: boolean;
    }) => (
      <div>
        {children}
        <button type="button" disabled={submitDisabled} onClick={() => onSubmit()}>
          Submit selection
        </button>
      </div>
    )
  ),
}));

const request = {
  id: 'request-1',
  title: 'Pick a dataset',
  description: 'Select the dataset file you would like to use.',
};

beforeEach(() => {
  capturedOnFileSelected = null;
});

describe('FilesetFileBlockingInput', () => {
  it('auto-submits when a fileset file is selected', async () => {
    const onSubmit = vi.fn<(submission: AgentBlockingInputSubmission) => void>();

    render(
      <FilesetFileBlockingInput
        request={request}
        workspace="default"
        onSubmit={onSubmit}
        defaultAcceptedFileTypes={['.jsonl']}
        missingSelectionMessage="Pick a dataset file"
        selectionDisplayLabel="Selected dataset"
        submitLabel="Select dataset"
        toValue={({ name, objectPath }) => ({
          dataset_fileset: name,
          dataset_path: objectPath,
        })}
      />
    );

    capturedOnFileSelected?.({
      path: 'train.jsonl',
      url: 'fileset://default/my-dataset/train.jsonl',
    });

    expect(onSubmit).toHaveBeenCalledWith({
      displayText: 'Selected dataset: my-dataset/train.jsonl',
      value: {
        dataset_fileset: 'my-dataset',
        dataset_path: 'train.jsonl',
      },
    });
  });

  it('disables manual submit until a dataset file is selected', () => {
    render(
      <FilesetFileBlockingInput
        request={request}
        workspace="default"
        onSubmit={vi.fn()}
        defaultAcceptedFileTypes={['.jsonl']}
        missingSelectionMessage="Pick a dataset file"
        selectionDisplayLabel="Selected dataset"
        submitLabel="Select dataset"
        toValue={({ name, objectPath }) => ({
          dataset_fileset: name,
          dataset_path: objectPath,
        })}
      />
    );

    expect(screen.getByRole('button', { name: 'Submit selection' })).toBeDisabled();
  });
});
