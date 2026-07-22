// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FILESET_NAME_MAX_LENGTH, toValidFilesetName } from '@nemo/common/src/utils/filesetName';
import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';

/** Sentinel ``evalConfig`` value that switches the form into create mode. */
export const CREATE_NEW = '__create_new__';

export const MODE_DEFAULT = 'default';
export const MODE_FILESET = 'fileset';

/** Suggested name for a new eval-config fileset (e.g. "wise-blue"). */
export const generateEvalConfigName = (): string => generateDefaultName({ length: 2 });

/** Default parallelism for a submitted eval (Studio default; the config value is a hint). */
export const DEFAULT_MAX_CONCURRENT_TASKS = 1;

export const buildEvalJobName = (filesetName: string): string => {
  const suffix = Math.random().toString(36).slice(2, 10).padEnd(8, '0');
  const base = toValidFilesetName(filesetName)
    .slice(0, FILESET_NAME_MAX_LENGTH - suffix.length - 1)
    .replace(/-+$/, '');
  return `${base}-${suffix}`;
};

// ---------------------------------------------------------------------------
// eval-config.json shape (stored in a fileset, read at submit)
// ---------------------------------------------------------------------------

/** One inline metric bundle as stored in eval-config.json (no judge_model —
 *  it is injected at submit). Kept loose: Studio does not re-validate the
 *  built-in metric shape, it only injects the model and fans it onto tasks. */
export interface InlineMetricBundle {
  bundle_kind: string;
  bundle_format_version: string;
  metric_type: string;
  metadata?: Record<string, unknown>;
  outputs?: unknown[];
  secrets?: Record<string, unknown>;
  payload: {
    kind: 'inline';
    metric: Record<string, unknown> & { model?: unknown };
  };
}

export interface EvalConfigTask {
  id: string;
  intent: string;
  inputs?: { instruction?: string | null };
  reference?: Record<string, unknown>;
}

/** The example template: inline tasks + one shared metric (metric not yet fanned). */
export interface EvalConfig {
  tasks: EvalConfigTask[];
  metric: InlineMetricBundle;
  max_concurrent_tasks?: number;
}

/** A task with the shared metric fanned onto it (judge baked in). */
export type EvalSpecTask = EvalConfigTask & { metrics: InlineMetricBundle[] };

/** The persisted yardstick stored in a fileset: tasks-with-metrics, no target.
 *  An `AgentEvalInputSpec` minus `target` — submit injects the per-run agent. */
export interface PersistedEvalSpec {
  tasks: EvalSpecTask[];
  max_concurrent_tasks?: number;
}

// ---------------------------------------------------------------------------
// Submit-time selections + request assembly
// ---------------------------------------------------------------------------

export interface SubmitSelections {
  workspace: string;
  /** Agent (bare name) to evaluate; used to build the generic target. */
  agent: string;
  /** Eval-config fileset name, stored under spec.benchmark.eval_config for display. */
  filesetName?: string;
}

/** Strip an optional ``workspace/`` prefix, returning the bare model/agent name. */
export const bareName = (value: string): string =>
  value.includes('/') ? (value.split('/').pop() ?? value) : value;

/** The generic agent target: the deployed agent's non-streaming ``/generate``. */
export const buildAgentTarget = (workspace: string, agent: string) => ({
  kind: 'agent' as const,
  agent: {
    format: 'generic' as const,
    url: `${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/${encodeURIComponent(workspace)}/agents/${encodeURIComponent(bareName(agent))}/-/generate`,
    name: bareName(agent),
    body: { input_message: '{{ instruction }}' },
    response_path: '$.value',
    stream: false,
  },
});

/** Set the metric's judge model to a ``workspace/name`` ModelRef (resolved to a
 *  reachable Model server-side). Does not mutate input. */
export const injectJudgeModel = (
  metric: InlineMetricBundle,
  judgeModel: string
): InlineMetricBundle => ({
  ...metric,
  payload: {
    ...metric.payload,
    metric: { ...metric.payload.metric, model: judgeModel },
  },
});

/** Fan the shared metric onto every task. A judge model is injected only when
 *  one is supplied; otherwise the template metric's own model is kept as-is. */
export const fanMetricOntoTasks = (
  config: EvalConfig,
  judgeModel: string | null
): EvalSpecTask[] => {
  const metric = judgeModel ? injectJudgeModel(config.metric, judgeModel) : config.metric;
  return config.tasks.map((task) => ({ ...task, metrics: [metric] }));
};

/** Build the persisted yardstick from an example template: fan the shared metric
 *  (judge baked in) onto every task. This is what gets stored in the fileset. */
export const buildPersistedSpec = (
  config: EvalConfig,
  judgeModel: string | null
): PersistedEvalSpec => ({
  tasks: fanMetricOntoTasks(config, judgeModel),
  max_concurrent_tasks: config.max_concurrent_tasks ?? DEFAULT_MAX_CONCURRENT_TASKS,
});

/** Build the ``agent-evaluate/jobs`` POST body from a persisted spec + selections. */
export const buildAgentEvalRequestBody = (
  spec: PersistedEvalSpec,
  selections: SubmitSelections
) => ({
  ...(selections.filesetName ? { name: buildEvalJobName(selections.filesetName) } : {}),
  spec: {
    tasks: spec.tasks,
    target: buildAgentTarget(selections.workspace, selections.agent),
    max_concurrent_tasks: spec.max_concurrent_tasks ?? DEFAULT_MAX_CONCURRENT_TASKS,
    ...(selections.filesetName
      ? { benchmark: { eval_config_fileset: selections.filesetName } }
      : {}),
  },
});

/** Parse an example template blob, validating the minimal required shape. */
export const parseEvalConfig = (text: string): EvalConfig => {
  const parsed = JSON.parse(text) as Partial<EvalConfig>;
  if (!Array.isArray(parsed.tasks) || parsed.tasks.length === 0) {
    throw new Error('eval-config.json must contain a non-empty "tasks" array');
  }
  if (!parsed.metric || typeof parsed.metric !== 'object') {
    throw new Error('eval-config.json must contain a "metric"');
  }

  const { payload } = parsed.metric;
  if (
    !payload ||
    typeof payload !== 'object' ||
    !payload.metric ||
    typeof payload.metric !== 'object'
  ) {
    throw new Error('eval-config.json "metric" must contain a "payload.metric" object');
  }
  return {
    tasks: parsed.tasks,
    metric: parsed.metric,
    max_concurrent_tasks: parsed.max_concurrent_tasks,
  };
};

/** Parse a persisted yardstick spec (the reuse path): tasks each carry their own
 *  metrics, no top-level ``metric``. Submitted as-is with only a target injected. */
export const parsePersistedSpec = (text: string): PersistedEvalSpec => {
  const parsed = JSON.parse(text) as Partial<PersistedEvalSpec>;
  if (!Array.isArray(parsed.tasks) || parsed.tasks.length === 0) {
    throw new Error('eval-config.json must contain a non-empty "tasks" array');
  }
  for (const task of parsed.tasks) {
    if (!Array.isArray(task.metrics) || task.metrics.length === 0) {
      throw new Error('eval-config.json every task must contain a non-empty "metrics" array');
    }
    const payload = task.metrics[0]?.payload;
    if (
      !payload ||
      typeof payload !== 'object' ||
      !payload.metric ||
      typeof payload.metric !== 'object'
    ) {
      throw new Error('eval-config.json task metric must contain a "payload.metric" object');
    }
  }
  return { tasks: parsed.tasks, max_concurrent_tasks: parsed.max_concurrent_tasks };
};
