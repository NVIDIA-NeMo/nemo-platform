// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { Badge, Button, Flex, Stack, Text } from '@nvidia/foundations-react-core';
import {
  EVAL_JOB_KIND_LABEL,
  evalJobDetailRoute,
  type EvalJobRow,
  hasMixedEvalKinds,
} from '@studio/api/evaluation/utils';
import { DetailPanel } from '@studio/routes/agents/AgentDetailRoute/overview/DetailPanel';
import { getAgentEvaluationsListRoute } from '@studio/routes/utils';
import type { FC } from 'react';
import { Link } from 'react-router-dom';

interface EvaluationsTabProps {
  workspace: string;
  evals: EvalJobRow[];
  onRunEvaluation: () => void;
}

/** Recent evaluation jobs for the agent, linking through to each run. */
export const EvaluationsTab: FC<EvaluationsTabProps> = ({ workspace, evals, onRunEvaluation }) => {
  const showKind = hasMixedEvalKinds(evals);

  return (
    <DetailPanel
      title="Recent evaluations"
      flush
      slotAction={
        <Button kind="secondary" size="small" onClick={onRunEvaluation}>
          Run evaluation
        </Button>
      }
    >
      {evals.length === 0 ? (
        <Stack gap="2" className="p-4">
          <Text color="secondary">No evaluation jobs found for this agent.</Text>
          <Link to={getAgentEvaluationsListRoute(workspace)} className="text-xs">
            View all evaluations →
          </Link>
        </Stack>
      ) : (
        <Stack gap="0">
          {evals.map((job, index) => (
            <Link
              key={job.id}
              to={evalJobDetailRoute(workspace, job)}
              className="text-inherit no-underline"
            >
              <Flex
                align="center"
                gap="2"
                className={`px-4 py-4 hover:bg-surface-hover ${index > 0 ? 'border-t border-base' : ''}`}
              >
                <Stack gap="1" className="min-w-0 flex-1">
                  <Text kind="body/semibold/md" className="truncate">
                    {job.name}
                  </Text>
                  <Flex align="center" gap="2" className="min-w-0">
                    {showKind && (
                      <Badge kind="outline" color="gray">
                        {EVAL_JOB_KIND_LABEL[job.kind]}
                      </Badge>
                    )}
                    <Text kind="body/regular/sm" color="secondary" className="truncate">
                      {job.configLabel ? `${job.configLabel} · ` : ''}
                      {job.created_at ? <RelativeTime datetime={job.created_at} /> : '—'}
                    </Text>
                  </Flex>
                </Stack>
                <StatusBadge status={job.status} />
              </Flex>
            </Link>
          ))}
          <div className="border-t border-base px-4 py-3">
            <Link to={getAgentEvaluationsListRoute(workspace)} className="text-xs">
              View all evaluations →
            </Link>
          </div>
        </Stack>
      )}
    </DetailPanel>
  );
};
