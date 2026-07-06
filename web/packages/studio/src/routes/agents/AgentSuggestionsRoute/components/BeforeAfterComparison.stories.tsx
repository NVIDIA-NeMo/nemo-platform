// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { Meta, StoryObj } from '@storybook/react';
import { BeforeAfterComparison } from '@studio/routes/agents/AgentSuggestionsRoute/components/BeforeAfterComparison';
import type { EvalUiState, ProfilerStats } from '@studio/routes/agents/AgentSuggestionsRoute/types';

const meta = {
  component: BeforeAfterComparison,
  title: 'Agents/Optimizer/BeforeAfterComparison',
  decorators: [
    (Story) => (
      // eslint-disable-next-line no-restricted-syntax
      <div style={{ maxWidth: '640px', padding: '16px' }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof BeforeAfterComparison>;

export default meta;
type Story = StoryObj<typeof meta>;

const profiler = (over: Partial<ProfilerStats>): ProfilerStats => ({
  avgTotalTokens: null,
  avgPromptTokens: null,
  avgCompletionTokens: null,
  llmLatencyP95Seconds: null,
  workflowRuntimeP95Seconds: null,
  ...over,
});

/** The happy path: the smaller model keeps recall high while cutting tokens and latency. */
export const Improved: Story = {
  args: {
    evalState: {
      jobName: 'eval-after',
      siblingAgentName: 'email-phishing-analyzer-nano',
      status: 'completed',
      scores: [
        { evaluator: 'recall', averageScore: 0.94 },
        { evaluator: 'precision', averageScore: 0.9 },
        { evaluator: 'f1', averageScore: 0.92 },
      ],
      profiler: profiler({
        avgTotalTokens: 820,
        llmLatencyP95Seconds: 1.1,
        workflowRuntimeP95Seconds: 1.9,
      }),
      detailHref: '#',
      baseline: {
        agentName: 'email-phishing-analyzer',
        jobName: 'eval-before',
        status: 'completed',
        scores: [
          { evaluator: 'recall', averageScore: 0.96 },
          { evaluator: 'precision', averageScore: 0.88 },
          { evaluator: 'f1', averageScore: 0.92 },
        ],
        profiler: profiler({
          avgTotalTokens: 1340,
          llmLatencyP95Seconds: 2.6,
          workflowRuntimeP95Seconds: 3.8,
        }),
      },
    } satisfies EvalUiState,
  },
};

/** A regression the reviewer should catch: recall drops when swapping models. */
export const RecallRegression: Story = {
  args: {
    evalState: {
      ...Improved.args!.evalState!,
      scores: [
        { evaluator: 'recall', averageScore: 0.71 },
        { evaluator: 'precision', averageScore: 0.93 },
        { evaluator: 'f1', averageScore: 0.8 },
      ],
    } satisfies EvalUiState,
  },
};

/** Both evals still in flight — every value renders as "—". */
export const InProgress: Story = {
  args: {
    evalState: {
      jobName: 'eval-after',
      siblingAgentName: 'email-phishing-analyzer-nano',
      status: 'queued',
      scores: [],
      profiler: null,
      detailHref: '#',
      baseline: {
        agentName: 'email-phishing-analyzer',
        jobName: 'eval-before',
        status: 'running',
        scores: [],
        profiler: null,
      },
    } satisfies EvalUiState,
  },
};

/** Runner without the profiler plugin: scores compare, cost rows are omitted. */
export const NoProfilerData: Story = {
  args: {
    evalState: {
      ...Improved.args!.evalState!,
      profiler: null,
      baseline: {
        ...Improved.args!.evalState!.baseline!,
        profiler: null,
      },
    } satisfies EvalUiState,
  },
};

/** Baseline re-score failed (e.g. original not deployed); after-side still shows. */
export const BaselineFailed: Story = {
  args: {
    evalState: {
      ...Improved.args!.evalState!,
      baseline: {
        agentName: 'email-phishing-analyzer',
        jobName: '',
        status: 'failed',
        scores: [],
        profiler: null,
        error: 'Deployment "email-phishing-analyzer" is not running.',
      },
    } satisfies EvalUiState,
  },
};
