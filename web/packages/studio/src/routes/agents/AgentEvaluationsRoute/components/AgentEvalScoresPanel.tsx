// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { AgentEvalAggregateScore } from '@studio/api/evaluation/agent-evaluations';
import { EvalAggregateScoresTable } from '@studio/components/evaluation/EvalAggregateScoresTable';
import { type FC } from 'react';

interface AgentEvalScoresPanelProps {
  scores: AgentEvalAggregateScore[];
}

const VIEW_PREFIX = 'view.';

export const AgentEvalScoresPanel: FC<AgentEvalScoresPanelProps> = ({ scores }) => {
  const ordered = [
    ...scores.filter((s) => s.name.startsWith(VIEW_PREFIX)),
    ...scores.filter((s) => !s.name.startsWith(VIEW_PREFIX)),
  ];

  return <EvalAggregateScoresTable scores={ordered} />;
};
