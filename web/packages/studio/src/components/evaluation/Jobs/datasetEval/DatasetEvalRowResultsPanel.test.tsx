// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  DatasetEvalRowResultsPanel,
  type DatasetEvalRow,
} from '@studio/components/evaluation/Jobs/datasetEval/DatasetEvalRowResultsPanel';
import { fireEvent, render, screen } from '@studio/tests/util/render';

const row = (requests: DatasetEvalRow['requests']): DatasetEvalRow => ({
  row_index: 0,
  item: { prompt: 'raw row', label: 'phishing' },
  sample: { output_text: 'phishing' },
  requests,
});

const openPanel = () => fireEvent.click(screen.getByRole('button', { name: /Row Results \(1\)/ }));

describe('DatasetEvalRowResultsPanel', () => {
  it('shows the empty state when there are no rows', () => {
    render(<DatasetEvalRowResultsPanel rows={[]} />);
    expect(
      screen.getByText('No per-row results recorded for this evaluation.')
    ).toBeInTheDocument();
  });

  it('renders the prompt from a chat-completions request body', async () => {
    render(
      <DatasetEvalRowResultsPanel
        rows={[row([{ request: { messages: [{ content: 'rendered prompt' }] } }])]}
      />
    );
    openPanel();

    expect(await screen.findByText('rendered prompt')).toBeInTheDocument();
  });

  it('renders the last message when the body carries a full transcript', async () => {
    render(
      <DatasetEvalRowResultsPanel
        rows={[
          row([
            { request: { messages: [{ content: 'system preamble' }, { content: 'the task' }] } },
          ]),
        ]}
      />
    );
    openPanel();

    expect(await screen.findByText('the task')).toBeInTheDocument();
  });

  it('falls back to input_message for jobs submitted before chat completions', async () => {
    render(
      <DatasetEvalRowResultsPanel rows={[row([{ request: { input_message: 'legacy body' } }])]} />
    );
    openPanel();

    expect(await screen.findByText('legacy body')).toBeInTheDocument();
  });

  it('falls back to the raw row when no request was recorded', async () => {
    render(<DatasetEvalRowResultsPanel rows={[row(undefined)]} />);
    openPanel();

    expect(await screen.findByText(/raw row/)).toBeInTheDocument();
  });
});
