// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Badge, Block, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import type { AgentEvalAggregateScore } from '@studio/api/evaluation/agent-evaluations';
import { formatScore, scoreColor } from '@studio/routes/agents/AgentEvaluationsRoute/evalScores';
import { type FC } from 'react';

interface AgentEvalScoresPanelProps {
  scores: AgentEvalAggregateScore[];
}

/** Aggregate score summary per metric: the mean as a colored badge plus the
 *  min/max range and sample count. Sourced from the `agent-eval-results`
 *  record (see this route's AGENTS.md). */
export const AgentEvalScoresPanel: FC<AgentEvalScoresPanelProps> = ({ scores }) => {
  if (scores.length === 0) {
    return <Block className="text-subtle">No scores recorded for this evaluation.</Block>;
  }

  return (
    <Stack gap="density-md">
      {scores.map((s) => {
        const total = s.count + s.nan_count;
        return (
          <Flex key={s.name} justify="between" align="center" gap="density-md" wrap="wrap">
            <Stack gap="density-xs" className="min-w-0">
              <Text kind="body/semibold/md" className="truncate">
                {s.name}
              </Text>
              <Text kind="body/regular/sm" color="secondary">
                {s.count}/{total} scored
                {typeof s.min === 'number' && typeof s.max === 'number'
                  ? ` · range ${formatScore(s.min)}–${formatScore(s.max)}`
                  : ''}
              </Text>
            </Stack>
            <Badge kind="solid" color={scoreColor(s.mean)}>
              {formatScore(s.mean)}
            </Badge>
          </Flex>
        );
      })}
    </Stack>
  );
};
