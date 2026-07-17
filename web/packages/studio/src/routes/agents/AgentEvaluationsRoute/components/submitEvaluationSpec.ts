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
  /** Judge model id from JudgeModelSelect (URN "workspace/name" or bare name). */
  judgeModel: string;
  /** Eval-config fileset name, stored as the job description for display in the detail view. */
  filesetName?: string;
}

/** Strip an optional ``workspace/`` prefix, returning the bare model/agent name. */
export const bareName = (value: string): string =>
  value.includes('/') ? (value.split('/').pop() ?? value) : value;

/** The judge model endpoint (IGW OpenAI-compatible route), format ``nim``. */
export const buildJudgeModel = (
  workspace: string,
  judgeModel: string
): { url: string; name: string; format: 'nim' } => ({
  url: `${PLATFORM_BASE_URL}/apis/inference-gateway/v2/workspaces/${encodeURIComponent(workspace)}/openai/-/v1`,
  name: bareName(judgeModel),
  format: 'nim',
});

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

/** Inject the judge model into a shared metric bundle (does not mutate input). */
export const injectJudgeModel = (
  metric: InlineMetricBundle,
  judgeModel: ReturnType<typeof buildJudgeModel>
): InlineMetricBundle => ({
  ...metric,
  payload: {
    ...metric.payload,
    metric: { ...metric.payload.metric, model: judgeModel },
  },
});

/** Fan the shared metric (with judge injected) onto every task. */
export const fanMetricOntoTasks = (
  config: EvalConfig,
  judgeModel: ReturnType<typeof buildJudgeModel>
): Array<EvalConfigTask & { metrics: InlineMetricBundle[] }> => {
  const metric = injectJudgeModel(config.metric, judgeModel);
  return config.tasks.map((task) => ({ ...task, metrics: [metric] }));
};

/** Build the full ``agent-evaluate/jobs`` POST body from a config + selections. */
export const buildAgentEvalRequestBody = (config: EvalConfig, selections: SubmitSelections) => {
  const judge = buildJudgeModel(selections.workspace, selections.judgeModel);
  return {
    ...(selections.filesetName ? { description: selections.filesetName } : {}),
    spec: {
      tasks: fanMetricOntoTasks(config, judge),
      target: buildAgentTarget(selections.workspace, selections.agent),
      max_concurrent_tasks: config.max_concurrent_tasks ?? DEFAULT_MAX_CONCURRENT_TASKS,
    },
  };
};

/** Parse an eval-config.json blob, validating the minimal required shape. */
export const parseEvalConfig = (text: string): EvalConfig => {
  const parsed = JSON.parse(text) as Partial<EvalConfig>;
  if (!Array.isArray(parsed.tasks) || parsed.tasks.length === 0) {
    throw new Error('eval-config.json must contain a non-empty "tasks" array');
  }
  if (!parsed.metric || typeof parsed.metric !== 'object') {
    throw new Error('eval-config.json must contain a "metric"');
  }
  return {
    tasks: parsed.tasks,
    metric: parsed.metric,
    max_concurrent_tasks: parsed.max_concurrent_tasks,
  };
};
