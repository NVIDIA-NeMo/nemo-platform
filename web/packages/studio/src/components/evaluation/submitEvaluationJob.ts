// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { FILESET_NAME_MAX_LENGTH, toValidFilesetName } from '@nemo/common/src/utils/filesetName';
import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import YAML from 'yaml';

/** Sentinel ``evalConfig`` value that switches the form into create mode. */
export const CREATE_NEW = '__create_new__';

export const MODE_DEFAULT = 'default';
/** Re-run an existing Experiment, which owns the fileset holding its eval config. */
export const MODE_EXPERIMENT = 'experiment';

/** Suggested name for a new experiment (e.g. "wise-blue"). */
export const generateEvalConfigName = (): string => generateDefaultName({ length: 2 });

/** The fileset that stores an experiment's eval config and data artifacts. */
export const filesetNameForExperiment = (experimentName: string): string =>
  `${experimentName}-data`;

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

/** A dataset-driven config: an `EvaluateInputSpec` minus the keys Studio owns per run.
 *  One metric set scores every row of a dataset, instead of each task carrying its own.
 *
 *  `dataset` and `prompt_template` are optional *as authored*: an uploaded config may
 *  leave either out and have it supplied from the form instead. Both are required by the
 *  time we submit — see {@link datasetEvalConfigError}. Any other key the author wrote is
 *  carried through untouched, so a valid `EvaluateInputSpec` field Studio has no opinion
 *  about (e.g. `field_mapping`) reaches the backend rather than being silently dropped. */
export interface DatasetEvalSpec extends Record<string, unknown> {
  dataset?: string | Record<string, unknown>[];
  metrics: InlineMetricBundle[];
  prompt_template?: string | Record<string, unknown>;
  field_mapping?: Record<string, unknown> | null;
}

export type EvalSpec = PersistedEvalSpec | DatasetEvalSpec;

/** Which evaluator endpoint a config targets, decided by its shape alone: `tasks[]` means
 *  task-based `agent-evaluate/jobs`, anything else is row-based `evaluate/jobs`. Keyed on
 *  `tasks` rather than `dataset` because an uploaded dataset-driven config is allowed to
 *  omit `dataset` and take it from the form. */
export const isTaskEvalSpec = (spec: EvalSpec): spec is PersistedEvalSpec =>
  Array.isArray((spec as PersistedEvalSpec).tasks);

export const isDatasetEvalSpec = (spec: EvalSpec): spec is DatasetEvalSpec => !isTaskEvalSpec(spec);

// ---------------------------------------------------------------------------
// Submit-time selections + request assembly
// ---------------------------------------------------------------------------

export interface SubmitSelections {
  workspace: string;
  /** Agent (bare name) to evaluate; used to build the generic target. */
  agent: string;
  /** Eval-config fileset name, stored under spec.labels.eval_config_fileset for display. */
  filesetName?: string;
  /** Experiment this run belongs to; names the job so it reads as one of that experiment's runs. */
  experimentName?: string;
  /** Name of an existing Intake Evaluation to publish results under. The job fails if it
   *  names nothing — the worker never creates it. Omitted means the run publishes nowhere. */
  evaluationId?: string;
}

/** ``spec.publication`` for a run that asked to publish, or nothing at all. ``agent_name`` is
 *  left off deliberately: the backend derives it from the agent target. */
const publicationSpec = (evaluationId: string | undefined) =>
  evaluationId ? { publication: { intake: { evaluation_id: evaluationId } } } : {};

/** ``{ name }`` for the job, stemmed from the experiment it belongs to and falling back to the
 *  fileset for a submit that names no experiment. Absent when neither is known. */
const jobName = (selections: SubmitSelections) => {
  const stem = selections.experimentName ?? selections.filesetName;
  return stem ? { name: buildEvalJobName(stem) } : {};
};

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
  ...jobName(selections),
  spec: {
    tasks: spec.tasks,
    target: buildAgentTarget(selections.workspace, selections.agent),
    max_concurrent_tasks: spec.max_concurrent_tasks ?? DEFAULT_MAX_CONCURRENT_TASKS,
    ...(selections.filesetName ? { labels: { eval_config_fileset: selections.filesetName } } : {}),
    ...publicationSpec(selections.evaluationId),
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
/** Keys Studio sets itself on every submit, so an authored value for any of them is replaced
 *  rather than rejected: `target` names the agent picked in the form, `params` is the
 *  failure-tolerant profile above, and `publication` routes results to this run's Evaluation.
 *  Everything else the author wrote survives — `EvaluateInputSpec` is `extra="forbid"`, so an
 *  unknown key surfaces as a 422 naming the field instead of vanishing on the way out. */
const STUDIO_OWNED_SPEC_KEYS = ['target', 'params', 'publication'] as const;

const withoutStudioOwnedKeys = (spec: DatasetEvalSpec): DatasetEvalSpec => {
  const authored = { ...spec };
  for (const key of STUDIO_OWNED_SPEC_KEYS) delete authored[key];
  return authored;
};

export const buildDatasetEvalRequestBody = (
  spec: DatasetEvalSpec,
  selections: SubmitSelections,
  judgeModel: string | null
) => {
  const authored = withoutStudioOwnedKeys(spec);
  return {
    ...jobName(selections),
    spec: {
      ...authored,
      metrics: judgeModel
        ? spec.metrics.map((metric) => injectJudgeModel(metric, judgeModel))
        : spec.metrics,
      target: buildDatasetAgentTarget(selections.workspace, selections.agent),
      params: AGENT_RUN_PARAMS,
      ...publicationSpec(selections.evaluationId),
    },
  };
};

/** Decode config text as JSON or YAML, chosen by extension and sniffed when there is none.
 *  Mirrors the platform CLI's ``--spec-file`` loader, so a file that runs through
 *  ``nemo evaluator evaluate submit`` is accepted here unchanged. YAML is a superset of
 *  JSON, so the order only decides which parser's message a malformed file reports. */
const decodeConfigText = (text: string, filename?: string): unknown => {
  const extension = /\.[^.]+$/.exec(filename?.toLowerCase() ?? '')?.[0];
  if (extension === '.json') return JSON.parse(text);
  if (extension === '.yaml' || extension === '.yml') return YAML.parse(text);
  try {
    return JSON.parse(text);
  } catch {
    return YAML.parse(text);
  }
};

/** Parse an eval config authored as JSON or YAML.
 *
 *  Both shapes are submitted close to as-authored: unrecognized top-level keys are kept
 *  rather than dropped, so a key the backend rejects fails loudly at submit instead of
 *  disappearing here. A dataset-driven config may omit `dataset` and `prompt_template`,
 *  which the form then supplies — {@link datasetEvalConfigError} is the gate before submit. */
export const parseEvalConfig = (text: string, filename?: string): EvalSpec => {
  const label = filename ? `"${filename}"` : 'the eval config';
  let raw: unknown;
  try {
    raw = decodeConfigText(text, filename);
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    throw new Error(`Could not parse ${label} as JSON or YAML: ${detail}`);
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error(`${label} must contain a top-level object`);
  }
  const parsed = raw as Partial<PersistedEvalSpec & DatasetEvalSpec> & Record<string, unknown>;

  if (parsed.tasks !== undefined) {
    if (!Array.isArray(parsed.tasks) || parsed.tasks.length === 0) {
      throw new Error(`${label} must contain a non-empty "tasks" array`);
    }
    for (const task of parsed.tasks) {
      if (!Array.isArray(task.metrics) || task.metrics.length === 0) {
        throw new Error(`${label} task "${task.id}" must contain a non-empty "metrics" array`);
      }
      for (const metric of task.metrics) {
        if (!metric?.payload?.metric || typeof metric.payload.metric !== 'object') {
          throw new Error(
            `${label} task "${task.id}" has a metric without a "payload.metric" object`
          );
        }
      }
    }
    return { ...parsed, tasks: parsed.tasks } as PersistedEvalSpec;
  }

  if (!Array.isArray(parsed.metrics) || parsed.metrics.length === 0) {
    throw new Error(`${label} must contain a non-empty "metrics" array, or a "tasks" array`);
  }
  for (const metric of parsed.metrics) {
    if (!metric?.payload?.metric || typeof metric.payload.metric !== 'object') {
      throw new Error(`${label} has a metric without a "payload.metric" object`);
    }
  }
  return { ...parsed, metrics: parsed.metrics } as DatasetEvalSpec;
};

/** Form-supplied values layered over an authored config. */
export interface DatasetEvalOverrides {
  /** ``<workspace>/<fileset>#<file>`` for a dataset uploaded alongside the config. */
  dataset?: string;
  promptTemplate?: string;
  judgeModel?: string | null;
}

/** Layer the form's overrides onto an authored config. Only values the user actually
 *  supplied win, so a complete uploaded config runs unchanged with every override blank,
 *  and a config missing a field is completed rather than replaced. */
export const applyDatasetEvalOverrides = (
  spec: DatasetEvalSpec,
  { dataset, promptTemplate, judgeModel }: DatasetEvalOverrides
): DatasetEvalSpec => ({
  ...spec,
  ...(dataset ? { dataset } : {}),
  ...(promptTemplate?.trim() ? { prompt_template: promptTemplate } : {}),
  metrics: judgeModel
    ? spec.metrics.map((metric) => injectJudgeModel(metric, judgeModel))
    : spec.metrics,
});

/** Why a dataset-driven config cannot be submitted yet, or null when it can. The backend
 *  requires both against an online target: `prompt_template` has no default here because a
 *  custom dataset's columns are arbitrary, so nothing can infer how a row becomes a request. */
export const datasetEvalConfigError = (spec: DatasetEvalSpec): string | null => {
  const hasDataset =
    typeof spec.dataset === 'string'
      ? spec.dataset.trim().length > 0
      : Array.isArray(spec.dataset) && spec.dataset.length > 0;
  if (!hasDataset) {
    return 'This config names no dataset. Upload a dataset file, or add a "dataset" reference to the config.';
  }
  if (!spec.prompt_template) {
    return 'This config has no prompt template. Add one under Optional configuration overrides, or add "prompt_template" to the config.';
  }
  return null;
};
