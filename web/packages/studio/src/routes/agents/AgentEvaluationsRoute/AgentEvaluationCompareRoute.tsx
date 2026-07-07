// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import {
  Badge,
  Block,
  Flex,
  PageHeader,
  Panel,
  Spinner,
  Stack,
  TableBody,
  TableDataCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
  Text,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import {
  fetchAgentEvalJob,
  isTerminalStatus,
  outputFilesetForJob,
  type AgentEvalJob,
} from '@studio/routes/agents/AgentEvaluationsRoute/api';
import { formatScore, scoreColor } from '@studio/routes/agents/AgentEvaluationsRoute/evalScores';
import { fetchEvalAverageScores } from '@studio/routes/agents/AgentSuggestionsRoute/api';
import {
  AGENT_EVAL_COMPARE_JOBS_PARAM,
  getAgentEvaluationDetailRoute,
  getAgentEvaluationsListRoute,
  getAgentsListRoute,
} from '@studio/routes/utils';
import { useQuery } from '@tanstack/react-query';
import { ClipboardList, FlaskConical } from 'lucide-react';
import { useMemo, type FC } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

interface ComparedEvaluation {
  name: string;
  job: AgentEvalJob | null;
  /** Evaluator → average score for this job. */
  scores: Map<string, number>;
}

const parseJobNames = (raw: string | null): string[] => {
  if (!raw) return [];
  const seen = new Set<string>();
  for (const part of raw.split(',')) {
    const name = part.trim();
    if (name) seen.add(name);
  }
  return [...seen];
};

export const AgentEvaluationCompareRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const [searchParams] = useSearchParams();
  const jobNames = useMemo(
    () => parseJobNames(searchParams.get(AGENT_EVAL_COMPARE_JOBS_PARAM)),
    [searchParams]
  );

  useBreadcrumbs({
    items: [
      { slotLabel: 'Agents', href: getAgentsListRoute(workspace) },
      { slotLabel: 'Evaluations', href: getAgentEvaluationsListRoute(workspace) },
      { slotLabel: 'Compare' },
    ],
  });

  const { data, isLoading } = useQuery({
    queryKey: ['agent-eval-compare', workspace, jobNames] as const,
    queryFn: async ({ signal }): Promise<ComparedEvaluation[]> => {
      return Promise.all(
        jobNames.map(async (name): Promise<ComparedEvaluation> => {
          const job = await fetchAgentEvalJob(workspace, name, signal);
          const outputFileset = job ? outputFilesetForJob(job) : null;
          const scores = new Map<string, number>();
          if (job && outputFileset && isTerminalStatus(job.status)) {
            const parsed = await fetchEvalAverageScores(workspace, outputFileset, signal);
            for (const s of parsed) scores.set(s.evaluator, s.averageScore);
          }
          return { name, job, scores };
        })
      );
    },
    enabled: !!workspace && jobNames.length > 0,
  });

  const evaluations = useMemo(() => data ?? [], [data]);

  // Union of evaluator names across every job, sorted, so the matrix has one
  // row per evaluator regardless of which jobs reported it.
  const evaluators = useMemo(() => {
    const set = new Set<string>();
    for (const ev of evaluations) for (const name of ev.scores.keys()) set.add(name);
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [evaluations]);

  // Best (highest) score per evaluator row, used to highlight the leader.
  const bestByEvaluator = useMemo(() => {
    const best = new Map<string, number>();
    for (const evaluator of evaluators) {
      let max = -Infinity;
      for (const ev of evaluations) {
        const score = ev.scores.get(evaluator);
        if (typeof score === 'number' && score > max) max = score;
      }
      if (Number.isFinite(max)) best.set(evaluator, max);
    }
    return best;
  }, [evaluators, evaluations]);

  const configs = useMemo(
    () => [...new Set(evaluations.map((e) => e.job?.spec.eval_config).filter(Boolean))] as string[],
    [evaluations]
  );

  if (jobNames.length === 0) {
    return (
      <Stack padding="density-2xl">
        <ErrorMessage
          header="Nothing to compare"
          message="No evaluations were selected. Open an evaluation and use “Compare” to pick jobs."
        />
      </Stack>
    );
  }

  if (isLoading) {
    return (
      <Flex align="center" justify="center" className="h-full w-full">
        <Spinner size="medium" aria-label="Loading comparison..." />
      </Flex>
    );
  }

  const foundEvaluations = evaluations.filter((e) => e.job);

  return (
    <AccessibleTitle title="Compare evaluations">
      <Stack className="w-full p-density-2xl min-h-full" gap="density-2xl">
        <PageHeader
          slotHeading="Compare evaluations"
          slotDescription="Side-by-side comparison of evaluation runs. Scores are the per-evaluator averages from each run's output fileset."
        />

        {configs.length === 1 && (
          <Flex gap="density-md" align="center" wrap="wrap">
            <Text kind="body/regular/sm" color="secondary">
              Eval config
            </Text>
            <Badge kind="outline" color="gray">
              {configs[0]}
            </Badge>
          </Flex>
        )}
        {configs.length > 1 && (
          <ErrorMessage
            header="Different eval configs"
            message={`These evaluations ran against different eval configs (${configs.join(
              ', '
            )}). Scores may not be directly comparable.`}
          />
        )}

        {foundEvaluations.length === 0 ? (
          <ErrorMessage
            header="Evaluations not found"
            message={`None of the selected evaluations were found in workspace "${workspace}".`}
          />
        ) : (
          <>
            <Panel
              slotHeading="Score comparison"
              slotIcon={<FlaskConical />}
              elevation="high"
              density="compact"
            >
              {evaluators.length === 0 ? (
                <Block className="text-subtle">
                  No evaluator scores are available for the selected evaluations.
                </Block>
              ) : (
                <Block className="overflow-x-auto">
                  <TableRoot layout="auto" density="compact" hoverableRows className="w-full">
                    <TableHead>
                      <TableRow>
                        <TableHeaderCell>Evaluator</TableHeaderCell>
                        {foundEvaluations.map((ev) => (
                          <TableHeaderCell key={ev.name}>
                            <Link
                              to={getAgentEvaluationDetailRoute(workspace, ev.name)}
                              className="no-underline"
                            >
                              <Text kind="body/semibold/sm" className="hover:underline">
                                {ev.name}
                              </Text>
                            </Link>
                          </TableHeaderCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {evaluators.map((evaluator) => {
                        const best = bestByEvaluator.get(evaluator);
                        return (
                          <TableRow key={evaluator}>
                            <TableDataCell>
                              <Text kind="body/regular/sm" className="capitalize">
                                {evaluator}
                              </Text>
                            </TableDataCell>
                            {foundEvaluations.map((ev) => {
                              const score = ev.scores.get(evaluator);
                              const hasScore = typeof score === 'number';
                              const isBest =
                                hasScore &&
                                typeof best === 'number' &&
                                score === best &&
                                foundEvaluations.length > 1;
                              return (
                                <TableDataCell key={ev.name}>
                                  <Flex gap="density-xs" align="center">
                                    <Badge
                                      kind={isBest ? 'solid' : 'outline'}
                                      color={hasScore ? scoreColor(score) : 'gray'}
                                    >
                                      {hasScore ? formatScore(score) : '–'}
                                    </Badge>
                                    {isBest && (
                                      <Text kind="body/regular/xs" color="secondary">
                                        best
                                      </Text>
                                    )}
                                  </Flex>
                                </TableDataCell>
                              );
                            })}
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </TableRoot>
                </Block>
              )}
            </Panel>

            <Panel
              slotHeading="Run details"
              slotIcon={<ClipboardList />}
              elevation="high"
              density="compact"
            >
              <div className="overflow-x-auto">
                <Flex gap="density-lg" align="stretch" className="min-w-min">
                  {foundEvaluations.map((ev) => {
                    const job = ev.job!;
                    return (
                      <Stack
                        key={ev.name}
                        gap="density-md"
                        className="min-w-[220px] flex-1 p-density-lg border border-subtle rounded"
                      >
                        <Link
                          to={getAgentEvaluationDetailRoute(workspace, ev.name)}
                          className="no-underline"
                        >
                          <Text kind="body/semibold/sm" className="truncate hover:underline">
                            {ev.name}
                          </Text>
                        </Link>
                        <StatusBadge status={job.status} />
                        <Stack gap="density-xs">
                          <Text kind="body/regular/xs" color="secondary">
                            Agent
                          </Text>
                          <Text kind="body/regular/sm" className="truncate">
                            {job.spec.agent ?? '–'}
                          </Text>
                        </Stack>
                        <Stack gap="density-xs">
                          <Text kind="body/regular/xs" color="secondary">
                            Created
                          </Text>
                          <Text kind="body/regular/sm">
                            <RelativeTime datetime={job.created_at} />
                          </Text>
                        </Stack>
                      </Stack>
                    );
                  })}
                </Flex>
              </div>
            </Panel>

            {evaluations.some((e) => !e.job) && (
              <Block className="text-subtle">
                Not shown:{' '}
                {evaluations
                  .filter((e) => !e.job)
                  .map((e) => e.name)
                  .join(', ')}{' '}
                (not found in this workspace).
              </Block>
            )}
          </>
        )}
      </Stack>
    </AccessibleTitle>
  );
};
