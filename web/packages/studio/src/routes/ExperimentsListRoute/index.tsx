// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getExperimentGroupRoute } from '@studio/routes/utils';
import { Flex, PageHeader, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import { Beaker, ChevronRight } from 'lucide-react';
import { type FC } from 'react';
import { Link } from 'react-router-dom';

import { EXPERIMENT_GROUPS, getCandidatesForGroup, getGroupLeader } from './fixtures';
import { useCandidates } from './store';

export const ExperimentsListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const candidates = useCandidates();

  return (
    <AccessibleTitle title="Experiments">
      <Stack gap="density-2xl" className="p-density-2xl">
        <PageHeader
          slotHeading={
            <Flex align="center" gap="density-sm">
              <Beaker />
              Experiments
            </Flex>
          }
          slotDescription="Group, compare, and validate offline optimization attempts before deploying changes."
        />

        <Stack gap="density-lg">
          {EXPERIMENT_GROUPS.map((group) => {
            const groupCandidates = getCandidatesForGroup(candidates, group.experiment_group_id);
            const leader = getGroupLeader(candidates, group.experiment_group_id);
            const leaderScore = leader?.evaluator_scores[0];
            return (
              <Link
                key={group.experiment_group_id}
                to={getExperimentGroupRoute(workspace, group.experiment_group_id)}
                className="block no-underline"
              >
                <Panel
                  elevation="high"
                  className="cursor-pointer hover:border-accent transition-colors"
                >
                  <Flex justify="between" align="start" gap="density-lg">
                    <Stack gap="density-sm" className="min-w-0 flex-1">
                      <Text kind="title/md">{group.name}</Text>
                      <Text kind="body/regular/sm" className="text-secondary">
                        {group.description}
                      </Text>
                      <Text kind="body/regular/xs" className="text-secondary">
                        Goal: {group.goal}
                      </Text>
                      {group.summary && (
                        <Text kind="body/regular/xs" className="text-secondary italic">
                          {group.summary}
                        </Text>
                      )}
                    </Stack>
                    <Stack gap="density-sm" align="end" className="shrink-0">
                      <Stack gap="density-xxs" align="end">
                        <Text kind="label/bold/xs" className="text-secondary uppercase">
                          Candidates
                        </Text>
                        <Text kind="title/lg">{groupCandidates.length}</Text>
                      </Stack>
                      {leader && leaderScore && (
                        <Stack gap="density-xxs" align="end">
                          <Text kind="label/bold/xs" className="text-secondary uppercase">
                            Leader · {leaderScore.evaluator_name}
                          </Text>
                          <Text kind="title/md">
                            {formatScore(leaderScore.mean, leaderScore.evaluator_name)}
                          </Text>
                        </Stack>
                      )}
                      <Text kind="body/regular/xs" className="text-secondary">
                        Created {formatAbsoluteTimestamp(group.created_at)}
                      </Text>
                    </Stack>
                    <ChevronRight className="shrink-0 self-center text-secondary" />
                  </Flex>
                </Panel>
              </Link>
            );
          })}
        </Stack>
      </Stack>
    </AccessibleTitle>
  );
};

const formatScore = (value: number, evaluatorName: string): string => {
  if (evaluatorName.toLowerCase().includes('latency')) {
    return `${value.toFixed(0)} ms`;
  }
  if (evaluatorName.toLowerCase().includes('cost')) {
    return `$${value.toFixed(3)}`;
  }
  return value.toFixed(3);
};
