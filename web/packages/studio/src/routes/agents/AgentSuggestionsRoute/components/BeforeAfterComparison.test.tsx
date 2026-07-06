// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BeforeAfterComparison } from '@studio/routes/agents/AgentSuggestionsRoute/components/BeforeAfterComparison';
import type { EvalUiState } from '@studio/routes/agents/AgentSuggestionsRoute/types';
import { render, screen } from '@studio/tests/util/render';

const completedState = (): EvalUiState => ({
  jobName: 'job-after',
  siblingAgentName: 'phish-nano',
  status: 'completed',
  scores: [{ evaluator: 'recall', averageScore: 0.92 }],
  profiler: {
    avgTotalTokens: 800,
    avgPromptTokens: 600,
    avgCompletionTokens: 200,
    llmLatencyP95Seconds: 1.2,
    workflowRuntimeP95Seconds: 2.0,
  },
  detailHref: '/x',
  baseline: {
    agentName: 'phish',
    jobName: 'job-before',
    status: 'completed',
    scores: [{ evaluator: 'recall', averageScore: 0.82 }],
    profiler: {
      avgTotalTokens: 1200,
      avgPromptTokens: 900,
      avgCompletionTokens: 300,
      llmLatencyP95Seconds: 2.4,
      workflowRuntimeP95Seconds: 3.5,
    },
  },
});

describe('BeforeAfterComparison', () => {
  it('shows before, after, and signed deltas for a quality metric', () => {
    render(<BeforeAfterComparison evalState={completedState()} />);
    expect(screen.getByText('recall')).toBeInTheDocument();
    expect(screen.getByText('0.82')).toBeInTheDocument(); // before
    expect(screen.getByText('0.92')).toBeInTheDocument(); // after
    expect(screen.getByText('+0.10')).toBeInTheDocument(); // improvement
  });

  it('renders cost rows where a reduction is the delta (lower is better)', () => {
    render(<BeforeAfterComparison evalState={completedState()} />);
    expect(screen.getByText('Avg tokens / item')).toBeInTheDocument();
    expect(screen.getByText('1,200')).toBeInTheDocument(); // before tokens
    expect(screen.getByText('800')).toBeInTheDocument(); // after tokens
    expect(screen.getByText('-400')).toBeInTheDocument(); // token reduction
    expect(screen.getByText('LLM latency (p95)')).toBeInTheDocument();
    expect(screen.getByText('-1.20 s')).toBeInTheDocument();
  });

  it('renders "—" when a run has not produced a value', () => {
    const state = completedState();
    state.baseline = { ...state.baseline!, profiler: null };
    render(<BeforeAfterComparison evalState={state} />);
    // Baseline tokens are unknown → before cell and delta both dash.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    // After tokens still render.
    expect(screen.getByText('800')).toBeInTheDocument();
  });

  it('surfaces a baseline error message', () => {
    const state = completedState();
    state.baseline = {
      agentName: 'phish',
      jobName: '',
      status: 'failed',
      scores: [],
      profiler: null,
      error: 'boom',
    };
    render(<BeforeAfterComparison evalState={state} />);
    expect(screen.getByText(/Baseline: boom/)).toBeInTheDocument();
  });
});
