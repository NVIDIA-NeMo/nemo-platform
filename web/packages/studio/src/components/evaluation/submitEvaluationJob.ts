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

/** ``RunConfigOnline`` for an agent target, shared by both submit paths. Serial by
 *  default: NAT reports workflow failures (including output truncation) as 422,
 *  which is not retried, so one failure would otherwise abort the whole job.
 *  ``ignore_request_failure`` degrades a failed row to NaN instead. */
const AGENT_RUN_PARAMS = {
  parallelism: 1,
  request_timeout: 300,
  max_retries: 3,
  ignore_request_failure: true,
} as const;

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

/** One inline metric bundle as stored in eval-config.json. Kept loose: Studio
 *  does not re-validate the built-in metric shape, it only overrides the judge
 *  model on metrics that name one. */
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

/** A task as authored in eval-config.json: carries its own metrics. */
export interface EvalSpecTask {
  id: string;
  intent: string;
  inputs?: { instruction?: string | null };
  reference?: Record<string, unknown>;
  metrics: InlineMetricBundle[];
  views?: Record<string, unknown>;
}

/** The eval config, both as authored under public/sample-agents and as stored in
 *  a fileset: an `AgentEvalInputSpec` minus `target` (target is per-run). */
export interface PersistedEvalSpec {
  tasks: EvalSpecTask[];
  max_concurrent_tasks?: number;
}

/** A dataset-driven config: an `EvaluateInputSpec` minus `target`. One metric set
 *  scores every row of a dataset, instead of each task carrying its own. */
export interface DatasetEvalSpec {
  dataset: string | Record<string, unknown>[];
  metrics: InlineMetricBundle[];
  prompt_template?: string | Record<string, unknown>;
  field_mapping?: Record<string, unknown> | null;
}

export type EvalSpec = PersistedEvalSpec | DatasetEvalSpec;

/** Which evaluator endpoint a config targets, decided by its shape alone: a
 *  `dataset` + `metrics` pair means row-based `evaluate/jobs`, `tasks[]` means
 *  task-based `agent-evaluate/jobs`. No extra registry metadata to keep in sync. */
export const isDatasetEvalSpec = (spec: EvalSpec): spec is DatasetEvalSpec =>
  'dataset' in spec && Array.isArray((spec as DatasetEvalSpec).metrics);

// ---------------------------------------------------------------------------
// Submit-time selections + request assembly
// ---------------------------------------------------------------------------

export interface SubmitSelections {
  workspace: string;
  /** Agent (bare name) to evaluate; used to build the generic target. */
  agent: string;
  /** Eval-config fileset name, stored under spec.labels.eval_config_fileset for display. */
  filesetName?: string;
}

/** Strip an optional ``workspace/`` prefix, returning the bare model/agent name. */
export const bareName = (value: string): string =>
  value.includes('/') ? (value.split('/').pop() ?? value) : value;

/** Chat completions is the one endpoint both config formats serve, so this needs no branch. */
const agentEndpoint = (workspace: string, agent: string, promptVar: string) => ({
  format: 'generic' as const,
  url: `${PLATFORM_BASE_URL}/apis/agents/v2/workspaces/${encodeURIComponent(workspace)}/agents/${encodeURIComponent(bareName(agent))}/-/v1/chat/completions`,
  name: bareName(agent),
  body: {
    model: bareName(agent),
    messages: [{ role: 'user', content: `{{ ${promptVar} }}` }],
    stream: false,
  },
  response_path: '$.choices[0].message.content',
  stream: false,
});

export const buildAgentTarget = (workspace: string, agent: string) => ({
  kind: 'agent' as const,
  agent: agentEndpoint(workspace, agent, 'instruction'),
  params: AGENT_RUN_PARAMS,
});

/** Override a metric's judge model with a ``workspace/name`` ModelRef (resolved
 *  to a reachable Model server-side). Metrics that name no model — string-check,
 *  exact-match, f1 — are returned untouched. Does not mutate input. */
export const injectJudgeModel = (
  metric: InlineMetricBundle,
  judgeModel: string
): InlineMetricBundle =>
  metric.payload?.metric && (metric.metric_type === 'llm-judge' || 'model' in metric.payload.metric)
    ? {
        ...metric,
        payload: {
          ...metric.payload,
          metric: { ...metric.payload.metric, model: judgeModel },
        },
      }
    : metric;

/** Apply the picked judge model across every task's metrics. With no judge
 *  supplied the config's own model strings are used as authored. */
export const applyJudgeModel = (
  tasks: EvalSpecTask[],
  judgeModel: string | null
): EvalSpecTask[] =>
  judgeModel
    ? tasks.map((task) => ({
        ...task,
        metrics: task.metrics.map((metric) => injectJudgeModel(metric, judgeModel)),
      }))
    : tasks;

/** Build the spec persisted to a fileset: the config as authored, with the
 *  picked judge model applied. */
export const buildPersistedSpec = (
  config: PersistedEvalSpec,
  judgeModel: string | null
): PersistedEvalSpec => ({
  tasks: applyJudgeModel(config.tasks, judgeModel),
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
    ...(selections.filesetName ? { labels: { eval_config_fileset: selections.filesetName } } : {}),
  },
});

/** The bare agent target for ``evaluate/jobs``. Unlike the agent-evaluate target
 *  this is NOT wrapped in {kind, agent}: EvaluateInputSpec forbids extra keys and
 *  takes the agent object directly. The body renders the row-based ``prompt``
 *  rather than a task ``instruction``. */
export const buildDatasetAgentTarget = (workspace: string, agent: string) =>
  agentEndpoint(workspace, agent, 'prompt');

/** Build the ``evaluate/jobs`` POST body from a dataset-driven config. ``params``
 *  must be exactly RunConfigOnline for an agent target, and ``prompt_template``
 *  is required — the job 500s without both. */
export const buildDatasetEvalRequestBody = (
  spec: DatasetEvalSpec,
  selections: SubmitSelections,
  judgeModel: string | null
) => ({
  ...(selections.filesetName ? { name: buildEvalJobName(selections.filesetName) } : {}),
  spec: {
    dataset: spec.dataset,
    metrics: judgeModel
      ? spec.metrics.map((metric) => injectJudgeModel(metric, judgeModel))
      : spec.metrics,
    target: buildDatasetAgentTarget(selections.workspace, selections.agent),
    prompt_template: spec.prompt_template,
    ...(spec.field_mapping ? { field_mapping: spec.field_mapping } : {}),
    params: AGENT_RUN_PARAMS,
  },
});

/** Parse an eval-config.json. Every task must carry its own ``metrics[]`` —
 *  the config is submitted as authored, with only the judge model and the
 *  per-run agent target applied on top. */
export const parseEvalConfig = (text: string): EvalSpec => {
  const raw = JSON.parse(text) as Partial<PersistedEvalSpec & DatasetEvalSpec>;

  if (raw.dataset !== undefined) {
    if (!Array.isArray(raw.metrics) || raw.metrics.length === 0) {
      throw new Error('a dataset-driven eval-config.json must contain a non-empty "metrics" array');
    }
    if (!raw.prompt_template) {
      throw new Error('a dataset-driven eval-config.json must contain a "prompt_template"');
    }
    return {
      dataset: raw.dataset,
      metrics: raw.metrics,
      prompt_template: raw.prompt_template,
      field_mapping: raw.field_mapping ?? null,
    };
  }

  const parsed = raw;
  if (!Array.isArray(parsed.tasks) || parsed.tasks.length === 0) {
    throw new Error('eval-config.json must contain "tasks" or a "dataset"');
  }
  for (const task of parsed.tasks) {
    if (!Array.isArray(task.metrics) || task.metrics.length === 0) {
      throw new Error(
        `eval-config.json task "${task.id}" must contain a non-empty "metrics" array`
      );
    }
    for (const metric of task.metrics) {
      if (!metric?.payload?.metric || typeof metric.payload.metric !== 'object') {
        throw new Error(
          `eval-config.json task "${task.id}" has a metric without a "payload.metric" object`
        );
      }
    }
  }
  return { tasks: parsed.tasks, max_concurrent_tasks: parsed.max_concurrent_tasks };
};
