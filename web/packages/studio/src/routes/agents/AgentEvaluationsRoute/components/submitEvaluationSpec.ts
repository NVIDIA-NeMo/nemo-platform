// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { generateDefaultName } from '@nemo/common/src/utils/generateDefaultName';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';

// Assembles the `agent-evaluate/jobs` request from a reusable `eval-config.json`
// (inline tasks + one shared inline metric) plus the submit-time selections
// (agent target + judge model). See this route's AGENTS.md for the contract.

/** Sentinel ``evalConfig`` value that switches the form into create mode. */
export const CREATE_NEW = '__create_new__';

export const MODE_DEFAULT = 'default';
export const MODE_FILESET = 'fileset';

/** Suggested name for a new eval-config fileset (e.g. "wise-blue"). */
export const generateEvalConfigName = (): string => generateDefaultName({ length: 2 });

/** Default parallelism for a submitted eval (Studio default; the config value is a hint). */
export const DEFAULT_MAX_CONCURRENT_TASKS = 1;

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

/** The reusable eval config: inline tasks + one shared metric. */
export interface EvalConfig {
  tasks: EvalConfigTask[];
  metric: InlineMetricBundle;
  max_concurrent_tasks?: number;
}

// ---------------------------------------------------------------------------
// Submit-time selections + request assembly
// ---------------------------------------------------------------------------

export interface SubmitSelections {
  workspace: string;
  /** Agent (bare name) to evaluate; used to build the generic target. */
  agent: string;
  /** Judge ModelRef ("workspace/name") from JudgeModelSelect, injected into the
   *  metric. Empty in chosen-fileset mode, where the config's own judge is kept. */
  judgeModel: string;
  /** Eval-config fileset name, stored as the job description for display in the detail view. */
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
 *  one is supplied (the "Use Example" path); otherwise the config's own judge
 *  ModelRef is kept as-is (chosen-fileset configs are self-contained). */
export const fanMetricOntoTasks = (
  config: EvalConfig,
  judgeModel: string | null
): Array<EvalConfigTask & { metrics: InlineMetricBundle[] }> => {
  const metric = judgeModel ? injectJudgeModel(config.metric, judgeModel) : config.metric;
  return config.tasks.map((task) => ({ ...task, metrics: [metric] }));
};

/** Build the full ``agent-evaluate/jobs`` POST body from a config + selections. */
export const buildAgentEvalRequestBody = (config: EvalConfig, selections: SubmitSelections) => ({
  ...(selections.filesetName ? { description: selections.filesetName } : {}),
  spec: {
    tasks: fanMetricOntoTasks(config, selections.judgeModel || null),
    target: buildAgentTarget(selections.workspace, selections.agent),
    max_concurrent_tasks: config.max_concurrent_tasks ?? DEFAULT_MAX_CONCURRENT_TASKS,
  },
});

/** Parse an eval-config.json blob, validating the minimal required shape. */
export const parseEvalConfig = (text: string): EvalConfig => {
  const parsed = JSON.parse(text) as Partial<EvalConfig>;
  if (!Array.isArray(parsed.tasks) || parsed.tasks.length === 0) {
    throw new Error('eval-config.json must contain a non-empty "tasks" array');
  }
  if (!parsed.metric || typeof parsed.metric !== 'object') {
    throw new Error('eval-config.json must contain a "metric"');
  }
  // Guard the one shape the client dereferences (injection reads payload.metric)
  // so a malformed bundle fails here, not with a TypeError at request build.
  // Metric-type/bounds validity is the backend's job (bundle is otherwise loose).
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
