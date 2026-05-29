// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getExperimentCandidateRoute } from '@studio/routes/utils';
import { Badge, Flex, PageHeader, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import { Award, Bot, User } from 'lucide-react';
import { type FC, useMemo } from 'react';
import { Link } from 'react-router-dom';

import {
  type AgentDatasetTuple,
  type Candidate,
  getAllAgentDatasetTuples,
  getCurrentBenchmark,
  useCandidates,
} from '../ExperimentsListRoute/store';

export const ExperimentBenchmarksRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const candidates = useCandidates();

  const tuples = useMemo(() => getAllAgentDatasetTuples(candidates), [candidates]);

  return (
    <AccessibleTitle title="Benchmarks">
      <Stack gap="density-2xl" className="p-density-2xl">
        <PageHeader
          slotHeading={
            <Flex align="center" gap="density-sm">
              <Award />
              Benchmarks
            </Flex>
          }
          slotDescription="The canonical comparison anchor for each (agent, dataset) pair. One Benchmark per pair; promoting a new Candidate atomically demotes the previous one."
        />

        {tuples.length === 0 ? (
          <Panel elevation="low">
            <Text kind="body/regular/sm" className="text-secondary">
              No Candidates in this workspace yet. Once Candidates exist, you can promote them to Benchmarks here.
            </Text>
          </Panel>
        ) : (
          <Panel elevation="high" className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-base">
                    <Th>Agent</Th>
                    <Th>Dataset</Th>
                    <Th>Current Benchmark</Th>
                    <Th>Updated</Th>
                    <Th>Source</Th>
                    <Th>Candidates</Th>
                  </tr>
                </thead>
                <tbody>
                  {tuples.map((tuple) => (
                    <BenchmarkRow
                      key={`${tuple.agent_name}::${tuple.dataset_id}`}
                      tuple={tuple}
                      benchmark={getCurrentBenchmark(candidates, tuple.agent_name, tuple.dataset_id)}
                      workspace={workspace}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
      </Stack>
    </AccessibleTitle>
  );
};

const Th: FC<{ children: React.ReactNode }> = ({ children }) => (
  <th className="px-density-md py-density-sm text-left text-xs font-bold uppercase text-secondary">
    {children}
  </th>
);

const Td: FC<{ children: React.ReactNode; className?: string }> = ({ children, className }) => (
  <td className={`px-density-md py-density-md align-top ${className ?? ''}`}>{children}</td>
);

interface BenchmarkRowProps {
  tuple: AgentDatasetTuple;
  benchmark: Candidate | undefined;
  workspace: string;
}

const BenchmarkRow: FC<BenchmarkRowProps> = ({ tuple, benchmark, workspace }) => (
  <tr className="border-b border-base hover:bg-surface-raised">
    <Td>
      <Text kind="label/bold/sm">{tuple.agent_name}</Text>
    </Td>
    <Td>
      <Stack gap="density-xxs">
        <Text kind="body/regular/sm">{tuple.dataset_name}</Text>
        {tuple.dataset_version && (
          <Text kind="body/regular/xs" className="text-secondary">
            {tuple.dataset_version}
          </Text>
        )}
      </Stack>
    </Td>
    <Td>
      {benchmark ? (
        <Stack gap="density-xxs">
          <Link
            to={getExperimentCandidateRoute(workspace, benchmark.candidate_id)}
            className="no-underline"
          >
            <Flex align="center" gap="density-xs">
              <Award className="text-accent shrink-0" size={14} />
              <Text kind="label/bold/sm">{benchmark.benchmark_name ?? benchmark.candidate_id}</Text>
            </Flex>
          </Link>
          {benchmark.benchmark_slug && (
            <Text kind="body/regular/xs" className="font-mono text-secondary">
              {benchmark.benchmark_slug}
            </Text>
          )}
          <Text kind="body/regular/xs" className="font-mono text-secondary">
            {benchmark.agent_version}
          </Text>
          {benchmark.evaluator_scores[0] && (
            <Text kind="body/regular/xs" className="text-secondary">
              {benchmark.evaluator_scores[0].evaluator_name}:{' '}
              <span className="font-bold">
                {formatScore(
                  benchmark.evaluator_scores[0].mean,
                  benchmark.evaluator_scores[0].evaluator_name,
                )}
              </span>
            </Text>
          )}
        </Stack>
      ) : (
        <Stack gap="density-xxs">
          <Text kind="body/regular/sm" className="text-secondary italic">
            No Benchmark yet
          </Text>
          <Text kind="body/regular/xs" className="text-secondary">
            Promote a Candidate to get started.
          </Text>
        </Stack>
      )}
    </Td>
    <Td>
      {benchmark?.benchmark_promoted_at ? (
        <Text kind="body/regular/sm" className="text-secondary">
          {formatAbsoluteTimestamp(benchmark.benchmark_promoted_at)}
        </Text>
      ) : (
        <Text kind="body/regular/sm" className="text-secondary">
          —
        </Text>
      )}
    </Td>
    <Td>
      {benchmark?.benchmark_promoted_via ? (
        <Flex align="center" gap="density-xs">
          {benchmark.benchmark_promoted_via === 'auto' ? (
            <Bot size={14} className="text-secondary" />
          ) : (
            <User size={14} className="text-secondary" />
          )}
          <Stack gap="density-xxs">
            <Badge kind="outline">{benchmark.benchmark_promoted_via}</Badge>
            {benchmark.benchmark_promoted_by && (
              <Text kind="body/regular/xs" className="text-secondary">
                {benchmark.benchmark_promoted_by}
              </Text>
            )}
          </Stack>
        </Flex>
      ) : (
        <Text kind="body/regular/sm" className="text-secondary">
          —
        </Text>
      )}
    </Td>
    <Td>
      <Text kind="body/regular/sm">{tuple.candidate_count}</Text>
    </Td>
  </tr>
);

const formatScore = (value: number, evaluatorName: string): string => {
  if (evaluatorName.toLowerCase().includes('latency')) {
    return `${value.toFixed(0)} ms`;
  }
  if (evaluatorName.toLowerCase().includes('cost')) {
    return `$${value.toFixed(3)}`;
  }
  return value.toFixed(3);
};
