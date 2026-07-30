// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { withOperators } from '@nemo/common/src/api/filterOperators';
import { jobsListJobs } from '@nemo/sdk/generated/platform/api';
import type {
  PlatformJobListSortField,
  PlatformJobResponse,
  PlatformJobsListFilter,
} from '@nemo/sdk/generated/platform/schema';
import {
  getAgentEvaluationDetailRoute,
  getEvaluationResultDetailsRoute,
} from '@studio/routes/utils';

export const EVALUATOR_JOB_SOURCES = ['nemo-evaluator', 'nemo-evaluator.agent-evaluate'] as const;

export type EvalJobKind = 'task' | 'dataset';

export interface EvalJobRow {
  id: string;
  name: string;
  status?: string;
  created_at?: string;
  kind: EvalJobKind;
  agentName: string | null;
  configLabel: string | null;
}

interface EvalJobSpec {
  dataset?: unknown;
  tasks?: unknown;
  benchmark?: { eval_config_fileset?: unknown };
  target?: {
    kind?: string;
    name?: string;
    agent?: { name?: string };
  };
}

const specOf = (job: PlatformJobResponse): EvalJobSpec => (job.spec ?? {}) as EvalJobSpec;

export const evalJobKind = (job: PlatformJobResponse): EvalJobKind =>
  specOf(job).dataset !== undefined ? 'dataset' : 'task';

const stripWorkspacePrefix = (name: string, workspace?: string): string => {
  const prefix = workspace ? `${workspace}/` : '';
  return prefix && name.startsWith(prefix) ? name.slice(prefix.length) : name;
};

export const targetNameForEvalJob = (job: PlatformJobResponse): string | null => {
  const target = specOf(job).target;
  if (!target) return null;
  const name = target.kind === 'agent' ? target.agent?.name : target.name;
  if (typeof name !== 'string' || name.length === 0) return null;
  return stripWorkspacePrefix(name, job.workspace);
};

export const evalJobConfigLabel = (job: PlatformJobResponse): string | null => {
  const spec = specOf(job);
  if (evalJobKind(job) === 'dataset') {
    if (typeof spec.dataset !== 'string' || !spec.dataset) return null;
    const [filesetRef] = spec.dataset.split('#');
    return filesetRef.split('/').pop() || filesetRef;
  }
  const fileset = spec.benchmark?.eval_config_fileset;
  return typeof fileset === 'string' && fileset.length > 0 ? fileset : null;
};

/** True when the list mixes paradigms — the only case where a per-row kind
 *  chip earns its space. */
export const hasMixedEvalKinds = (rows: EvalJobRow[]): boolean =>
  new Set(rows.map((row) => row.kind)).size > 1;

export const evalJobDetailRoute = (workspace: string, row: EvalJobRow): string =>
  row.kind === 'dataset'
    ? getEvaluationResultDetailsRoute(workspace, row.name)
    : getAgentEvaluationDetailRoute(workspace, row.name);

export const EVAL_JOB_KIND_LABEL: Record<EvalJobKind, string> = {
  task: 'Task-driven',
  dataset: 'Dataset-driven',
};

export const toEvalJobRow = (job: PlatformJobResponse): EvalJobRow => ({
  id: job.id || job.name,
  name: job.name,
  status: job.status,
  created_at: job.created_at,
  kind: evalJobKind(job),
  agentName: targetNameForEvalJob(job),
  configLabel: evalJobConfigLabel(job),
});

const PAGE_SIZE = 50;

export const fetchEvaluatorJobs = async (
  workspace: string,
  signal: AbortSignal
): Promise<PlatformJobResponse[]> => {
  const all: PlatformJobResponse[] = [];
  let page = 1;
  while (true) {
    const res = await jobsListJobs(
      workspace,
      {
        page,
        page_size: PAGE_SIZE,
        sort: '-created_at' as PlatformJobListSortField,
        filter: withOperators<PlatformJobsListFilter>({
          source: { $in: [...EVALUATOR_JOB_SOURCES] },
        }),
      },
      signal
    );
    const batch = res?.data ?? [];
    all.push(...batch);
    if (batch.length < PAGE_SIZE) break;
    page++;
  }
  return all;
};
