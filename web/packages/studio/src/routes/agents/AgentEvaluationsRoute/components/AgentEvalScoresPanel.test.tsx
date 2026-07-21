// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AgentEvalScoresPanel } from '@studio/routes/agents/AgentEvaluationsRoute/components/AgentEvalScoresPanel';
import { render, screen } from '@studio/tests/util/render';

describe('AgentEvalScoresPanel', () => {
  it('reports scored and NaN rows without subtracting NaNs twice', () => {
    render(
      <AgentEvalScoresPanel
        scores={[
          {
            name: 'llm-judge.accuracy',
            count: 4,
            nan_count: 1,
            mean: 0.75,
            min: 0,
            max: 1,
            score_type: 'range',
          },
        ]}
      />
    );

    expect(screen.getByText('4/5 scored · range 0.000–1.000')).toBeInTheDocument();
    expect(screen.getByText('0.750')).toBeInTheDocument();
  });

  it('renders the rubric distribution and mode category for rubric scores', () => {
    render(
      <AgentEvalScoresPanel
        scores={[
          {
            name: 'llm-judge.helpfulness',
            count: 3,
            nan_count: 0,
            mean: 0.667,
            score_type: 'rubric',
            mode_category: 'partially_helpful',
            rubric_distribution: [
              { label: 'unhelpful', value: 0, count: 1 },
              { label: 'partially_helpful', value: 0.5, count: 2 },
              { label: 'helpful', value: 1, count: 0 },
            ],
          },
        ]}
      />
    );

    expect(screen.getByText('Most frequent: partially_helpful')).toBeInTheDocument();
    expect(screen.getByText('unhelpful: 1')).toBeInTheDocument();
    expect(screen.getByText('partially_helpful: 2')).toBeInTheDocument();
    expect(screen.getByText('helpful: 0')).toBeInTheDocument();
    expect(screen.getByText('0.667')).toBeInTheDocument();
  });
});
