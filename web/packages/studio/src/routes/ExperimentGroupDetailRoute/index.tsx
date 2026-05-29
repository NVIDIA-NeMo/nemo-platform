// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getExperimentsRoute } from '@studio/routes/utils';
import {
  Badge,
  Flex,
  PageHeader,
  Panel,
  Stack,
  TabsContent,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { Award, Beaker, ChevronLeft } from 'lucide-react';
import { type FC, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  type Candidate,
  type DatasetSlice,
  getCandidatesForGroup,
  getCompatibleBenchmarks,
  getDatasetSlicesForGroup,
  getExperimentGroup,
} from '../ExperimentsListRoute/fixtures';
import { useCandidates } from '../ExperimentsListRoute/store';
import { getExperimentCandidateRoute } from '@studio/routes/utils';

export const ExperimentGroupDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { experimentGroupId } = useParams<{ experimentGroupId: string }>();
  const group = experimentGroupId ? getExperimentGroup(experimentGroupId) : undefined;
  const allCandidates = useCandidates();

  const candidates = useMemo(
    () => (experimentGroupId ? getCandidatesForGroup(allCandidates, experimentGroupId) : []),
    [allCandidates, experimentGroupId],
  );
  const datasetSlices = useMemo(
    () => (experimentGroupId ? getDatasetSlicesForGroup(allCandidates, experimentGroupId) : []),
    [allCandidates, experimentGroupId],
  );

  const [activeDataset, setActiveDataset] = useState<string | undefined>(
    () => datasetSlices[0]?.dataset_id,
  );

  if (!group) {
    return (
      <Stack gap="density-md" className="p-density-2xl">
        <Text kind="title/md">Experiment Group not found</Text>
        <Link to={getExperimentsRoute(workspace)} className="no-underline">
          <Flex align="center" gap="density-xs" className="text-accent">
            <ChevronLeft />
            <Text kind="body/regular/sm">Back to Experiments</Text>
          </Flex>
        </Link>
      </Stack>
    );
  }

  const activeSlice = datasetSlices.find((s) => s.dataset_id === activeDataset) ?? datasetSlices[0];

  return (
    <AccessibleTitle title={group.name}>
      <Stack gap="density-2xl" className="p-density-2xl">
        <Stack gap="density-md">
          <Link to={getExperimentsRoute(workspace)} className="no-underline">
            <Flex align="center" gap="density-xs" className="text-secondary">
              <ChevronLeft size={16} />
              <Text kind="body/regular/sm">Experiments</Text>
            </Flex>
          </Link>
          <PageHeader
            slotHeading={
              <Flex align="center" gap="density-sm">
                <Beaker />
                {group.name}
              </Flex>
            }
            slotDescription={group.description}
          />
          <Panel elevation="low" className="bg-surface-raised">
            <Stack gap="density-xs">
              <Text kind="label/bold/xs" className="text-secondary uppercase">
                Goal
              </Text>
              <Text kind="body/regular/sm">{group.goal}</Text>
              {group.summary && (
                <>
                  <Text kind="label/bold/xs" className="text-secondary uppercase mt-density-sm">
                    Summary
                  </Text>
                  <Text kind="body/regular/sm" className="italic">
                    {group.summary}
                  </Text>
                </>
              )}
            </Stack>
          </Panel>
        </Stack>

        {datasetSlices.length === 0 ? (
          <Panel elevation="low">
            <Text kind="body/regular/sm" className="text-secondary">
              No candidates in this group yet.
            </Text>
          </Panel>
        ) : (
          <TabsRoot
            value={activeSlice?.dataset_id}
            onValueChange={(value) => setActiveDataset(value)}
          >
            <Stack gap="density-md">
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
              {datasetSlices.map((slice) => (
                <TabsContent key={slice.dataset_id} value={slice.dataset_id}>
                  <DatasetLeaderboard slice={slice} candidates={candidates} workspace={workspace} />
                </TabsContent>
              ))}
            </Stack>
          </TabsRoot>
        )}
      </Stack>
    </AccessibleTitle>
  );
};

// ---------------------------------------------------------------------------
// Leaderboard for one dataset slice. Renders sticky Benchmark anchor rows on top
// then ranked Candidate rows (by the first evaluator's mean — POC heuristic).
// ---------------------------------------------------------------------------

interface DatasetLeaderboardProps {
  slice: DatasetSlice;
  candidates: Candidate[];
  workspace: string;
}

const DatasetLeaderboard: FC<DatasetLeaderboardProps> = ({ slice, candidates, workspace }) => {
  const allCandidates = useCandidates();
  const sliceCandidates = candidates.filter((c) => c.dataset_id === slice.dataset_id);
  const agentNames = new Set(sliceCandidates.map((c) => c.agent_name));

  const benchmarks = useMemo(() => {
    const all: Candidate[] = [];
    for (const agentName of agentNames) {
      all.push(...getCompatibleBenchmarks(allCandidates, agentName, slice.dataset_id));
    }
    return all;
  }, [allCandidates, agentNames, slice.dataset_id]);

  const evaluators = useMemo(() => {
    const seen = new Set<string>();
    for (const c of [...benchmarks, ...sliceCandidates]) {
      for (const score of c.evaluator_scores) {
        seen.add(score.evaluator_name);
      }
    }
    return Array.from(seen);
  }, [benchmarks, sliceCandidates]);

  const ranked = useMemo(() => {
    return [...sliceCandidates].sort((a, b) => {
      const aScore = a.evaluator_scores[0]?.mean ?? 0;
      const bScore = b.evaluator_scores[0]?.mean ?? 0;
      return bScore - aScore;
    });
  }, [sliceCandidates]);

  return (
    <Panel elevation="high" className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-base">
              <Th className="w-[60px]">Rank</Th>
              <Th>Candidate</Th>
              <Th>Agent version</Th>
              {evaluators.map((evaluator) => (
                <Th key={evaluator} className="text-right">
                  {evaluator}
                </Th>
              ))}
              <Th className="text-right">Runs</Th>
            </tr>
          </thead>
          <tbody>
            {benchmarks.map((bench) => (
              <BenchmarkRow
                key={bench.candidate_id}
                candidate={bench}
                evaluators={evaluators}
                workspace={workspace}
              />
            ))}
            {ranked.map((candidate, index) => (
              <CandidateRow
                key={candidate.candidate_id}
                rank={index + 1}
                candidate={candidate}
                evaluators={evaluators}
                workspace={workspace}
              />
            ))}
            {ranked.length === 0 && (
              <tr>
                <td colSpan={evaluators.length + 4} className="p-density-lg text-center">
                  <Text kind="body/regular/sm" className="text-secondary">
                    No candidates on this dataset yet.
                  </Text>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Panel>
  );
};

// ---------------------------------------------------------------------------
// Cell components
// ---------------------------------------------------------------------------

const Th: FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <th
    className={`px-density-md py-density-sm text-left text-xs font-bold uppercase text-secondary ${className ?? ''}`}
  >
    {children}
  </th>
);

const Td: FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <td className={`px-density-md py-density-sm align-top ${className ?? ''}`}>{children}</td>
);

interface BenchmarkRowProps {
  candidate: Candidate;
  evaluators: string[];
  workspace: string;
}

const BenchmarkRow: FC<BenchmarkRowProps> = ({ candidate, evaluators, workspace }) => (
  <tr className="border-b border-base bg-accent/5 sticky top-0">
    <Td>
      <Award className="text-accent" size={20} />
    </Td>
    <Td>
      <Stack gap="density-xxs">
        <Flex align="center" gap="density-xs">
          <Link
            to={getExperimentCandidateRoute(workspace, candidate.candidate_id)}
            className="no-underline"
          >
            <Text kind="label/bold/sm">{candidate.benchmark_name ?? candidate.candidate_id}</Text>
          </Link>
          <Badge kind="outline">Benchmark</Badge>
        </Flex>
        {candidate.benchmark_description && (
          <Text kind="body/regular/xs" className="text-secondary">
            {candidate.benchmark_description}
          </Text>
        )}
        {candidate.benchmark_promoted_at && (
          <Text kind="body/regular/xs" className="text-secondary">
            Updated {new Date(candidate.benchmark_promoted_at).toLocaleString()}
            {candidate.benchmark_promoted_via && ` · ${candidate.benchmark_promoted_via}`}
          </Text>
        )}
      </Stack>
    </Td>
    <Td>
      <Text kind="body/regular/sm" className="font-mono text-xs">
        {candidate.agent_version}
      </Text>
    </Td>
    {evaluators.map((evaluator) => {
      const score = candidate.evaluator_scores.find((s) => s.evaluator_name === evaluator);
      return (
        <Td key={evaluator} className="text-right">
          {score ? (
            <Text kind="label/bold/sm">{formatScore(score.mean, evaluator)}</Text>
          ) : (
            <Text kind="body/regular/sm" className="text-secondary">
              —
            </Text>
          )}
        </Td>
      );
    })}
    <Td className="text-right">
      <Text kind="body/regular/sm">{candidate.run_count}</Text>
    </Td>
  </tr>
);

interface CandidateRowProps {
  rank: number;
  candidate: Candidate;
  evaluators: string[];
  workspace: string;
}

const CandidateRow: FC<CandidateRowProps> = ({ rank, candidate, evaluators, workspace }) => {
  const headlineEvaluator = candidate.evaluator_scores[0]?.evaluator_name;
  return (
    <tr className="border-b border-base hover:bg-surface-raised">
      <Td>
        <Text kind="label/bold/sm" className="text-secondary">
          {rank}
        </Text>
      </Td>
      <Td>
        <Stack gap="density-xxs">
          <Link
            to={getExperimentCandidateRoute(workspace, candidate.candidate_id)}
            className="no-underline"
          >
            <Text kind="label/bold/sm">{candidate.candidate_id}</Text>
          </Link>
          {candidate.summary && (
            <Text kind="body/regular/xs" className="text-secondary italic">
              {candidate.summary}
            </Text>
          )}
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
      </Td>
      <Td>
        <Text kind="body/regular/sm" className="font-mono text-xs">
          {candidate.agent_version}
        </Text>
      </Td>
      {evaluators.map((evaluator) => {
        const score = candidate.evaluator_scores.find((s) => s.evaluator_name === evaluator);
        const isHeadline = evaluator === headlineEvaluator;
        return (
          <Td key={evaluator} className="text-right">
            {score ? (
              <Text kind={isHeadline ? 'label/bold/sm' : 'body/regular/sm'}>
                {formatScore(score.mean, evaluator)}
              </Text>
            ) : (
              <Text kind="body/regular/sm" className="text-secondary">
                —
              </Text>
            )}
          </Td>
        );
      })}
      <Td className="text-right">
        <Text kind="body/regular/sm">{candidate.run_count}</Text>
      </Td>
    </tr>
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
