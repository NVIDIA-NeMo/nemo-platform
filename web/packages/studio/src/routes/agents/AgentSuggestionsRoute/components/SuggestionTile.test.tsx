// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SuggestionTile } from '@studio/routes/agents/AgentSuggestionsRoute/components/SuggestionTile';
import type {
  EvalUiState,
  OptimizationSuggestion,
} from '@studio/routes/agents/AgentSuggestionsRoute/types';
import { render, screen, within } from '@studio/tests/util/render';
import userEvent from '@testing-library/user-event';

const guardrailsSuggestion = (): OptimizationSuggestion => ({
  type: 'guardrails',
  title: 'No guardrails on phish (nemotron-70b)',
  detail: 'Routes directly through the inference gateway.',
  agent: 'phish',
  model: 'nemotron-70b',
  severity: 'high',
  apply: [{ method: 'POST', path: '/apis/guardrails/v2/workspaces/default/configs', body: {} }],
  apply_description: 'Creates a guarded copy.',
});

const modelOptSuggestion = (): OptimizationSuggestion => ({
  type: 'model_optimization',
  title: 'Apply tuned hyperparameters to phish',
  detail: 'Tuned temperature/top_p.',
  agent: 'phish',
  severity: 'medium',
  apply: [
    {
      method: 'POST',
      path: '/apis/agents/v2/workspaces/default/agents',
      body: { name: 'phish-t' },
    },
    {
      method: 'POST',
      path: '/apis/agents/v2/workspaces/default/deployments',
      body: { agent: 'phish-t' },
    },
    {
      method: 'POST',
      path: '/apis/agents/v2/workspaces/default/jobs/evaluate',
      body: { spec: { agent: 'phish-t' } },
    },
  ],
});

const evalState = (overrides: Partial<EvalUiState> = {}): EvalUiState => ({
  jobName: 'job-1',
  siblingAgentName: 'phish-t',
  status: 'completed',
  scores: [],
  detailHref: '/x',
  ...overrides,
});

const statusRow = () => screen.getByTestId('suggestion-tile-apply-status');

describe('SuggestionTile — apply status', () => {
  it('shows a blue "Applying…" badge while the apply is in flight', () => {
    render(<SuggestionTile suggestion={guardrailsSuggestion()} onApply={vi.fn()} isApplying />);
    expect(within(statusRow()).getByText('Applying…')).toBeInTheDocument();
  });

  it('shows a green success badge on success', () => {
    render(<SuggestionTile suggestion={guardrailsSuggestion()} onApply={vi.fn()} isApplied />);
    expect(within(statusRow()).getByText('Success!')).toBeInTheDocument();
  });

  it('shows a red "Failed" badge and the error on failure', () => {
    render(
      <SuggestionTile
        suggestion={guardrailsSuggestion()}
        onApply={vi.fn()}
        applyError="Deployment failed: boom"
      />
    );
    const row = statusRow();
    expect(within(row).getByText('Failed')).toBeInTheDocument();
    expect(within(row).getByText('Deployment failed: boom')).toBeInTheDocument();
  });

  it('failed wins over applied when a partial apply left an error', () => {
    render(
      <SuggestionTile
        suggestion={{ ...guardrailsSuggestion(), applied: true }}
        onApply={vi.fn()}
        applyError="deploy never went ready"
      />
    );
    expect(within(statusRow()).getByText('Failed')).toBeInTheDocument();
    expect(within(statusRow()).queryByText('Success!')).not.toBeInTheDocument();
  });

  it('renders no status row before an apply is attempted', () => {
    render(<SuggestionTile suggestion={guardrailsSuggestion()} onApply={vi.fn()} />);
    expect(screen.queryByTestId('suggestion-tile-apply-status')).not.toBeInTheDocument();
  });
});

describe('SuggestionTile — retry on failed eval', () => {
  it('offers an enabled Retry button when an applied suggestion has a failed eval', async () => {
    const onApply = vi.fn();
    render(
      <SuggestionTile
        suggestion={{ ...modelOptSuggestion(), applied: true }}
        onApply={onApply}
        isApplied
        evalState={evalState({ status: 'failed', error: 'bad eval config' })}
      />
    );
    const btn = screen.getByRole('button', { name: /Retry evaluation/ });
    expect(btn).toBeEnabled();
    await userEvent.click(btn);
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('offers Retry when only the baseline ("before") side failed', () => {
    render(
      <SuggestionTile
        suggestion={{ ...modelOptSuggestion(), applied: true }}
        onApply={vi.fn()}
        isApplied
        evalState={evalState({
          status: 'completed',
          baseline: {
            agentName: 'phish',
            jobName: 'job-0',
            status: 'failed',
            scores: [],
            profiler: null,
          },
        })}
      />
    );
    expect(screen.getByRole('button', { name: /Retry evaluation/ })).toBeEnabled();
  });

  it('shows a disabled "Applied" button (no retry) once the eval completed', () => {
    render(
      <SuggestionTile
        suggestion={{ ...modelOptSuggestion(), applied: true }}
        onApply={vi.fn()}
        isApplied
        evalState={evalState({ status: 'completed' })}
      />
    );
    expect(screen.queryByRole('button', { name: /Retry evaluation/ })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Apply suggestion/ })).toBeDisabled();
  });
});
