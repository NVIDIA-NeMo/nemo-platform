// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { RelativeTime } from '@nemo/common/src/components/RelativeTime';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import {
  Badge,
  Block,
  Button,
  Card,
  Flex,
  PageHeader,
  Select,
  Spinner,
  Stack,
  Text,
  TextInput,
} from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { fetchAgentEvalJobs } from '@studio/routes/agents/AgentEvaluationsRoute/api';
import { SubmitEvaluationModal } from '@studio/routes/agents/AgentEvaluationsRoute/components/SubmitEvaluationModal';
import { getAgentEvaluationDetailRoute, getAgentsListRoute } from '@studio/routes/utils';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState, type FC } from 'react';
import { Link } from 'react-router-dom';

const AGENT_EVAL_JOBS_QUERY_KEY = (workspace: string) => ['agent-eval-jobs', workspace] as const;

const STATUS_FILTER_OPTIONS = [
  { value: '', children: 'All statuses' },
  { value: 'running', children: 'Running' },
  { value: 'queued', children: 'Queued' },
  { value: 'completed', children: 'Completed' },
  { value: 'failed', children: 'Failed' },
  { value: 'cancelled', children: 'Cancelled' },
];

const SORT_OPTIONS = [
  { value: 'created_desc', children: 'Newest first' },
  { value: 'created_asc', children: 'Oldest first' },
  { value: 'name_asc', children: 'Name (A→Z)' },
  { value: 'name_desc', children: 'Name (Z→A)' },
];

type SortKey = 'created_desc' | 'created_asc' | 'name_asc' | 'name_desc';

const STATUS_BUCKETS: Record<string, string[]> = {
  running: ['running'],
  queued: ['queued', 'pending', 'created'],
  completed: ['completed', 'succeeded', 'success'],
  failed: ['failed', 'error'],
  cancelled: ['cancelled', 'canceled'],
};

const matchesStatus = (status: string, filter: string): boolean => {
  if (!filter) return true;
  const bucket = STATUS_BUCKETS[filter] ?? [filter];
  return bucket.includes((status ?? '').toLowerCase());
};

export const AgentEvaluationsListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const [submitOpen, setSubmitOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState('');
  const [agentSearch, setAgentSearch] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('created_desc');
  useBreadcrumbs({
    items: [
      { slotLabel: 'Agents', href: getAgentsListRoute(workspace) },
      { slotLabel: 'Evaluations' },
    ],
  });

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: AGENT_EVAL_JOBS_QUERY_KEY(workspace),
    queryFn: ({ signal }) => fetchAgentEvalJobs(workspace, signal),
    enabled: !!workspace,
    // Eval jobs transition through queued → running → completed; refetch
    // every 10s while the user is on the page so the list reflects state
    // changes without a manual reload.
    refetchInterval: 10_000,
  });

  const jobs = useMemo(() => {
    const all = data ?? [];
    const search = agentSearch.trim().toLowerCase();
    const filtered = all.filter((job) => {
      if (!matchesStatus(job.status, statusFilter)) return false;
      if (search) {
        const agent = (job.spec.agent ?? '').toLowerCase();
        const name = job.name.toLowerCase();
        if (!agent.includes(search) && !name.includes(search)) return false;
      }
      return true;
    });
    const sorted = [...filtered].sort((a, b) => {
      switch (sortKey) {
        case 'created_asc':
          return a.created_at.localeCompare(b.created_at);
        case 'name_asc':
          return a.name.localeCompare(b.name);
        case 'name_desc':
          return b.name.localeCompare(a.name);
        case 'created_desc':
        default:
          return b.created_at.localeCompare(a.created_at);
      }
    });
    return sorted;
  }, [data, statusFilter, agentSearch, sortKey]);

  return (
    <AccessibleTitle title={`Agent Evaluations for ${workspace}`}>
      <Stack className="min-h-full" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Agent Evaluations"
          slotDescription="Evaluation jobs run against deployed agents — submitted by the optimizer apply flow or directly via the evaluate-agent job API."
          slotActions={
            <Button kind="primary" color="brand" onClick={() => setSubmitOpen(true)}>
              Run Evaluation
            </Button>
          }
        />

        {isLoading && (
          <Flex align="center" justify="center" className="min-h-[200px]">
            <Spinner size="medium" aria-label="Loading evaluation jobs..." />
          </Flex>
        )}

        {error && !isLoading && (
          <Stack gap="density-md">
            <ErrorMessage
              header="Failed to load evaluation jobs"
              message={error instanceof Error ? error.message : 'Unknown error'}
              slotFooter={
                <Button kind="secondary" size="small" onClick={() => void refetch()}>
                  Retry
                </Button>
              }
            />
          </Stack>
        )}

        {!isLoading && !error && (data ?? []).length > 0 && (
          <Flex gap="density-md" wrap="wrap" align="end">
            <Block className="flex-1 min-w-[200px]">
              <TextInput
                placeholder="Search by agent or job name"
                value={agentSearch}
                onChange={(e) => setAgentSearch(e.target.value)}
              />
            </Block>
            <Block className="min-w-[180px]">
              <Select
                value={statusFilter}
                items={STATUS_FILTER_OPTIONS}
                onValueChange={(v) => setStatusFilter(v)}
              />
            </Block>
            <Block className="min-w-[180px]">
              <Select
                value={sortKey}
                items={SORT_OPTIONS}
                onValueChange={(v) => setSortKey(v as SortKey)}
              />
            </Block>
          </Flex>
        )}

        {!isLoading && !error && (data ?? []).length === 0 && (
          <ErrorMessage
            header="No evaluation jobs yet"
            message="Apply a model_optimization suggestion or submit an evaluate-agent job to see results here."
          />
        )}

        {!isLoading && !error && (data ?? []).length > 0 && jobs.length === 0 && (
          <Block className="text-subtle">No evaluations match the current filters.</Block>
        )}

        {!isLoading && !error && jobs.length > 0 && (
          <Stack gap="density-md">
            {jobs.map((job) => (
              <Link
                key={job.name}
                to={getAgentEvaluationDetailRoute(workspace, job.name)}
                className="no-underline text-inherit"
              >
                <Card className="hover:bg-surface-hover">
                  <Flex justify="between" align="center" gap="density-md" wrap="wrap">
                    <Stack gap="density-xs" className="flex-1 min-w-0">
                      <Text kind="title/xs" className="truncate">
                        {job.name}
                      </Text>
                      <Flex gap="density-md" wrap="wrap">
                        {job.spec.agent && (
                          <Badge kind="outline" color="gray">
                            Agent: {job.spec.agent}
                          </Badge>
                        )}
                        {job.spec.eval_config && (
                          <Badge kind="outline" color="gray">
                            Config: {job.spec.eval_config}
                          </Badge>
                        )}
                      </Flex>
                    </Stack>
                    <Stack gap="density-xs" className="text-right">
                      <Block>
                        <StatusBadge status={job.status} />
                      </Block>
                      <Text kind="body/regular/sm" color="secondary">
                        Created <RelativeTime datetime={job.created_at} />
                      </Text>
                    </Stack>
                  </Flex>
                </Card>
              </Link>
            ))}
          </Stack>
        )}
      </Stack>
      <SubmitEvaluationModal
        open={submitOpen}
        onClose={() => setSubmitOpen(false)}
        workspace={workspace}
      />
    </AccessibleTitle>
  );
};
