// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { PlatformJobResponse } from '@nemo/sdk/generated/platform/schema';
import {
  getAgentEvaluationDetailRoute,
  getEvaluationResultDetailsRoute,
} from '@studio/routes/utils';

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

export const hasMixedEvalKinds = (rows: EvalJobRow[]): boolean =>
  new Set(rows.map((row) => row.kind)).size > 1;

export const evalJobDetailRoute = (workspace: string, row: EvalJobRow): string =>
  row.kind === 'dataset'
    ? getEvaluationResultDetailsRoute(workspace, row.name)
    : getAgentEvaluationDetailRoute(workspace, row.name);

export const EVAL_JOB_KIND_LABEL: Record<EvalJobKind, string> = {
  task: 'Task-Driven',
  dataset: 'Dataset-Driven',
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

/** Task result shape with metrics and scores for evaluation results. */
interface EvaluationResultTasks {
  [taskName: string]: {
    metrics?: Record<string, { scores?: Record<string, { value?: unknown }> }>;
  };
}

interface MetricWithScore {
  task: string;
  metric: string;
  key: string;
  value: string;
}

export const getMetricsAsList = (tasks?: EvaluationResultTasks): MetricWithScore[] => {
  const metricsAsList: MetricWithScore[] = [];

  if (!tasks) return metricsAsList;

  for (const [taskName, task] of Object.entries(tasks)) {
    const t = task as EvaluationResultTasks[string];
    if (!t?.metrics) continue;

    for (const [metricName, metricValue] of Object.entries(t.metrics)) {
      const mv = metricValue as { scores?: Record<string, { value?: unknown }> };
      if (!mv?.scores) continue;

      for (const [key, valueObj] of Object.entries(mv.scores)) {
        const vo = valueObj as { value?: unknown };
        if (vo?.value == null) continue;

        metricsAsList.push({
          task: taskName,
          metric: metricName,
          key,
          value: String(vo.value).substring(0, 5),
        });
      }
    }
  }

  return metricsAsList;
};
