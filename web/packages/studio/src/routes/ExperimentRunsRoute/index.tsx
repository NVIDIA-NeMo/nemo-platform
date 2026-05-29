// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getExperimentCandidateRoute } from '@studio/routes/utils';
import {
  Badge,
  Flex,
  Grid,
  PageHeader,
  Panel,
  Stack,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { ArrowUpRight, Award, ListOrdered, Trophy } from 'lucide-react';
import { type FC, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import {
  type Candidate,
  EXPERIMENT_GROUPS,
  getAllDatasetSlices,
  getCandidatesForDataset,
  getDatasetTotals,
} from '../ExperimentsListRoute/fixtures';
import { useCandidates } from '../ExperimentsListRoute/store';

export const ExperimentRunsRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const candidates = useCandidates();
  const datasetSlices = useMemo(() => getAllDatasetSlices(candidates), [candidates]);
  const [activeDataset, setActiveDataset] = useState<string | undefined>(
    () => datasetSlices[0]?.dataset_id,
  );

  const activeSlice =
    datasetSlices.find((s) => s.dataset_id === activeDataset) ?? datasetSlices[0];

  const ranked = useMemo(
    () => (activeSlice ? getCandidatesForDataset(candidates, activeSlice.dataset_id) : []),
    [candidates, activeSlice],
  );
  const topRun = ranked[0];
  const totals = activeSlice
    ? getDatasetTotals(candidates, activeSlice.dataset_id)
    : { candidate_count: 0, total_runs: 0 };

  const groupNameById = useMemo(
    () => new Map(EXPERIMENT_GROUPS.map((g) => [g.experiment_group_id, g.name])),
    [],
  );

  return (
    <AccessibleTitle title="Runs">
      <Stack gap="density-2xl" className="p-density-2xl">
        <PageHeader
          slotHeading={
            <Flex align="center" gap="density-sm">
              <ListOrdered />
              Runs
            </Flex>
          }
          slotDescription="Every Candidate across all Experiment Groups, ranked within the active dataset."
        />

        {datasetSlices.length === 0 ? (
          <Panel elevation="low">
            <Text kind="body/regular/sm" className="text-secondary">
              No runs yet.
            </Text>
          </Panel>
        ) : (
          <TabsRoot
            value={activeSlice?.dataset_id}
            onValueChange={(value) => setActiveDataset(value)}
          >
            <Stack gap="density-lg">
              <TabsList>
                {datasetSlices.map((slice) => (
                  <TabsTrigger key={slice.dataset_id} value={slice.dataset_id}>
                    {slice.name}
                    {slice.dataset_version && (
                      <Text kind="body/regular/xs" className="ml-density-xs text-secondary">
                        {slice.dataset_version}
                      </Text>
                    )}
                  </TabsTrigger>
                ))}
              </TabsList>

              {topRun && (
                <TopRunCard
                  candidate={topRun}
                  workspace={workspace}
                  groupName={
                    topRun.experiment_group_id
                      ? groupNameById.get(topRun.experiment_group_id)
                      : undefined
                  }
                  datasetName={activeSlice?.name ?? ''}
                />
              )}

              <Stack gap="density-sm">
                <Text kind="body/regular/xs" className="text-secondary uppercase">
                  {ranked.length} runs · sorted by{' '}
                  {ranked[0]?.evaluator_scores[0]?.evaluator_name ?? 'primary metric'}
                  {totals.total_runs > 0 && ` · ${totals.total_runs} evaluation runs total`}
                </Text>
                <Panel elevation="high" className="overflow-hidden">
                  <Stack gap="0">
                    {ranked.map((candidate, index) => (
                      <RunRow
                        key={candidate.candidate_id}
                        rank={index + 1}
                        candidate={candidate}
                        workspace={workspace}
                        groupName={
                          candidate.experiment_group_id
                            ? groupNameById.get(candidate.experiment_group_id)
                            : undefined
                        }
                      />
                    ))}
                    {ranked.length === 0 && (
                      <div className="p-density-lg text-center">
                        <Text kind="body/regular/sm" className="text-secondary">
                          No candidates on this dataset yet.
                        </Text>
                      </div>
                    )}
                  </Stack>
                </Panel>
              </Stack>
            </Stack>
          </TabsRoot>
        )}
      </Stack>
    </AccessibleTitle>
  );
};

// ---------------------------------------------------------------------------
// Top Run hero card (Vanessa-style)
// ---------------------------------------------------------------------------

interface TopRunCardProps {
  candidate: Candidate;
  workspace: string;
  groupName?: string;
  datasetName: string;
}

const TopRunCard: FC<TopRunCardProps> = ({ candidate, workspace, groupName, datasetName }) => {
  return (
    <Panel elevation="high">
      <Stack gap="density-md">
        <Flex align="center" gap="density-xs">
          <Trophy size={14} className="text-accent" />
          <Text kind="label/bold/xs" className="text-secondary uppercase">
            Top run · {datasetName}
          </Text>
        </Flex>
        <Stack gap="density-xs">
          <Link
            to={getExperimentCandidateRoute(workspace, candidate.candidate_id)}
            className="no-underline"
          >
            <Flex align="center" gap="density-xs" className="text-foreground">
              <Text kind="title/lg" className="font-mono break-all">
                {candidate.candidate_id}
              </Text>
              <ArrowUpRight className="text-secondary" />
            </Flex>
          </Link>
          <Flex align="center" gap="density-sm" wrap="wrap">
            <Text kind="body/regular/xs" className="text-secondary uppercase">
              {candidate.agent_name}
            </Text>
            <Text kind="body/regular/xs" className="text-secondary">
              ·
            </Text>
            <Text kind="body/regular/xs" className="text-secondary font-mono">
              {candidate.agent_version}
            </Text>
            {candidate.is_benchmark && <Badge kind="outline">Benchmark</Badge>}
            {groupName && (
              <>
                <Text kind="body/regular/xs" className="text-secondary">
                  ·
                </Text>
                <Text kind="body/regular/xs" className="text-secondary">
                  {groupName}
                </Text>
              </>
            )}
          </Flex>
        </Stack>
        <Grid className="grid-cols-2 md:grid-cols-4 gap-density-lg">
          {candidate.evaluator_scores.map((score) => (
            <Stack key={score.evaluator_name} gap="density-xxs">
              <Text kind="body/regular/xs" className="text-secondary uppercase">
                {score.evaluator_name}
              </Text>
              <Text kind="title/md">{formatScore(score.mean, score.evaluator_name)}</Text>
            </Stack>
          ))}
          <Stack gap="density-xxs">
            <Text kind="body/regular/xs" className="text-secondary uppercase">
              Eval Runs
            </Text>
            <Text kind="title/md">{candidate.run_count}</Text>
          </Stack>
        </Grid>
      </Stack>
    </Panel>
  );
};

// ---------------------------------------------------------------------------
// One row in the ranked list
// ---------------------------------------------------------------------------

interface RunRowProps {
  rank: number;
  candidate: Candidate;
  workspace: string;
  groupName?: string;
}

const RunRow: FC<RunRowProps> = ({ rank, candidate, workspace, groupName }) => {
  const target = getExperimentCandidateRoute(workspace, candidate.candidate_id);

  const content = (
    <Flex
      align="center"
      gap="density-md"
      className="px-density-lg py-density-md border-b border-base hover:bg-surface-raised transition-colors"
    >
      <Text kind="label/bold/sm" className="text-secondary w-[32px] shrink-0">
        {rank}
      </Text>
      <Stack gap="density-xxs" className="flex-1 min-w-0">
        <Flex align="center" gap="density-xs" className="min-w-0">
          {candidate.is_benchmark && <Award className="text-accent shrink-0" size={14} />}
          <Text kind="label/bold/sm" className="font-mono text-xs break-all">
            {candidate.candidate_id}
          </Text>
          <ArrowUpRight className="text-secondary shrink-0" size={14} />
        </Flex>
        <Flex align="center" gap="density-sm" wrap="wrap">
          <Text kind="body/regular/xs" className="text-secondary uppercase">
            {candidate.agent_name}
          </Text>
          <Text kind="body/regular/xs" className="text-secondary font-mono">
            {candidate.agent_version}
          </Text>
          {groupName && (
            <>
              <Text kind="body/regular/xs" className="text-secondary">
                ·
              </Text>
              <Text kind="body/regular/xs" className="text-secondary">
                {groupName}
              </Text>
            </>
          )}
          {candidate.is_benchmark && <Badge kind="outline">Benchmark</Badge>}
        </Flex>
        {candidate.producer_metadata && (
          <Flex gap="density-xs" wrap="wrap" className="mt-density-xxs">
            {Object.entries(candidate.producer_metadata).map(([k, v]) => (
              <Badge key={k} kind="outline">
                {k}: {String(v)}
              </Badge>
            ))}
          </Flex>
        )}
      </Stack>
      <Flex gap="density-lg" align="center" className="shrink-0">
        {candidate.evaluator_scores.map((score) => (
          <Stack key={score.evaluator_name} gap="density-xxs" align="end">
            <Text kind="body/regular/xs" className="text-secondary uppercase whitespace-nowrap">
              {score.evaluator_name}
            </Text>
            <Text kind="label/bold/sm">{formatScore(score.mean, score.evaluator_name)}</Text>
          </Stack>
        ))}
        <Stack gap="density-xxs" align="end">
          <Text kind="body/regular/xs" className="text-secondary uppercase whitespace-nowrap">
            Runs
          </Text>
          <Text kind="label/bold/sm">{candidate.run_count}</Text>
        </Stack>
      </Flex>
    </Flex>
  );

  return (
    <Link to={target} className="block no-underline">
      {content}
    </Link>
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
