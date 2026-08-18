// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { PlatformJobResponse } from '@nemo/sdk/generated/platform/schema';
import {
  getAgentEvaluationDetailRoute,
  getEvaluationResultDetailsRoute,
} from '@studio/routes/utils';
import { isPlainObject } from '@studio/util/functions';

export type EvalJobKind = 'task' | 'dataset';

export interface EvalJobRow {
  id: string;
  name: string;
  status?: string;
  created_at?: string;
  kind: EvalJobKind;
  agentName: string | null;
  configLabel: string | null;
  /** Intake Evaluation the run publishes to, when it asked to. The join key between a job and its
   *  published results — absent for a run submitted without `publication.intake`. */
  evaluationName: string | null;
}

const asRecord = (value: unknown): Record<string, unknown> | undefined =>
  isPlainObject(value) ? value : undefined;

const asNonEmptyString = (value: unknown): string | undefined =>
  typeof value === 'string' && value.length > 0 ? value : undefined;

const specOf = (job: PlatformJobResponse): Record<string, unknown> => job.spec ?? {};

export const evalJobKind = (job: PlatformJobResponse): EvalJobKind =>
  specOf(job).dataset !== undefined ? 'dataset' : 'task';

const stripWorkspacePrefix = (name: string, workspace?: string): string => {
  const prefix = workspace ? `${workspace}/` : '';
  return prefix && name.startsWith(prefix) ? name.slice(prefix.length) : name;
};

export const targetNameForEvalJob = (job: PlatformJobResponse): string | null => {
  const target = asRecord(specOf(job).target);
  if (!target) return null;
  const name =
    target.kind === 'agent'
      ? asNonEmptyString(asRecord(target.agent)?.name)
      : asNonEmptyString(target.name);
  if (!name) return null;
  return stripWorkspacePrefix(name, job.workspace);
};

export const evalJobConfigLabel = (job: PlatformJobResponse): string | null => {
  const spec = specOf(job);
  if (evalJobKind(job) === 'dataset') {
    const dataset = asNonEmptyString(spec.dataset);
    if (!dataset) return null;
    const [filesetRef] = dataset.split('#');
    return filesetRef.split('/').pop() || filesetRef;
  }
  return asNonEmptyString(asRecord(spec.benchmark)?.eval_config_fileset) ?? null;
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

export const publishedEvaluationName = (job: PlatformJobResponse): string | null => {
  const intake = asRecord(asRecord(specOf(job).publication)?.intake);
  return asNonEmptyString(intake?.evaluation_id) ?? null;
};

export const toEvalJobRow = (job: PlatformJobResponse): EvalJobRow => ({
  id: job.id || job.name,
  name: job.name,
  status: job.status,
  created_at: job.created_at,
  kind: evalJobKind(job),
  agentName: targetNameForEvalJob(job),
  configLabel: evalJobConfigLabel(job),
  evaluationName: publishedEvaluationName(job),
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
