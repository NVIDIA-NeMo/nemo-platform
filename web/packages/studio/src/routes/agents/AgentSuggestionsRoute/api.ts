// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { customFetch } from '@nemo/sdk/generated/fetchers/platform';
import {
  filesCreateFileset,
  filesDownloadFile,
  filesListFilesetFiles,
  filesUploadFile,
  modelsListModels,
} from '@nemo/sdk/generated/platform/api';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema/ModelEntity';
import { PLATFORM_BASE_URL } from '@studio/constants/environment';
import {
  SAMPLE_EVAL_CONFIG_PATH,
  SAMPLE_EVAL_DATA_JSON,
  SAMPLE_EVAL_DATA_PATH,
  SAMPLE_EVAL_YAML,
} from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import type {
  AgentListing,
  ApplyResult,
  EvalJobStatus,
  EvalJobStatusResponse,
  EvalScore,
  OptimizationSuggestion,
  SnapshotShape,
  SuggestionApplyMethod,
  SuggestionApplySpec,
  WaitForDeploymentsOptions,
  WaitForEvalJobOptions,
} from '@studio/routes/agents/AgentSuggestionsRoute/types';
import {
  parseSuggestions,
  serializeSuggestions,
  suggestionIdentity,
} from '@studio/routes/agents/AgentSuggestionsRoute/utils';
import { toError } from '@studio/util/logger';

export const TELEMETRY_FILESET = 'nemo-agent-telemetry';
export const OPTIMIZER_FILESET = 'nemo-agent-optimizer';
export const SUGGESTIONS_PATH = 'optimizer_suggestions.jsonl';
export const SNAPSHOT_PATH = 'optimizer_snapshot.json';
export const SUGGESTIONS_PREVIOUS_PATH = 'optimizer_suggestions.previous.jsonl';
export const SNAPSHOT_PREVIOUS_PATH = 'optimizer_snapshot.previous.json';

const isNotFoundError = (err: unknown): boolean => {
  const e = err as { response?: { status?: number }; status?: number };
  return e?.response?.status === 404 || e?.status === 404;
};

// Helpers that swallow other errors must still re-throw these — otherwise a
// stale run keeps producing results after abort() and can overwrite a fresher
// run's JSONL.
export const isCanceledError = (err: unknown): boolean => {
  const e = err as { name?: string; code?: string };
  return e?.name === 'AbortError' || e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED';
};

const MODELS_PAGE_SIZE = 200;
const AGENTS_PAGE_SIZE = 100;
const DEPLOYMENTS_PAGE_SIZE = 100;
const CONTENT_SAFETY_SAMPLE_CHARS = 2000;

export { CONTENT_SAFETY_MODEL_RE } from '@studio/routes/agents/AgentSuggestionsRoute/utils';

export const fetchAgents = async (
  workspace: string,
  signal: AbortSignal
): Promise<AgentListing[]> => {
  const all: AgentListing[] = [];
  let page = 1;
  while (true) {
    const res = await customFetch<{ data?: AgentListing[] }>({
      url: `/apis/agents/v2/workspaces/${encodeURIComponent(workspace)}/agents`,
      method: 'GET',
      params: { page, page_size: AGENTS_PAGE_SIZE },
      signal,
    });
    const batch = res?.data ?? [];
    all.push(...batch);
    if (batch.length < AGENTS_PAGE_SIZE) break;
    page++;
  }
  return all;
};

export const fetchModels = async (
  workspace: string,
  signal: AbortSignal
): Promise<ModelEntity[]> => {
  const allModels: ModelEntity[] = [];
  let page = 1;
  while (true) {
    const res = await modelsListModels(
      workspace,
      { page, page_size: MODELS_PAGE_SIZE, verbose: true },
      signal
    );
    const batch = (res?.data ?? []) as ModelEntity[];
    allModels.push(...batch);
    if (batch.length < MODELS_PAGE_SIZE) break;
    page++;
  }
  return allModels;
};

// 404 → '' (telemetry fileset is optional).
export const fetchPiiSample = async (workspace: string, signal: AbortSignal): Promise<string> => {
  try {
    const listing = await filesListFilesetFiles(workspace, TELEMETRY_FILESET, undefined, signal);
    const files = (listing?.data ?? []).filter((f) => f.path.endsWith('.jsonl'));
    if (files.length === 0) return '';
    const largest = [...files].sort((a, b) => (b.size ?? 0) - (a.size ?? 0))[0];
    const blob = await filesDownloadFile(workspace, TELEMETRY_FILESET, largest.path, signal);
    return blob ? await blob.text() : '';
  } catch (err) {
    if (isNotFoundError(err)) return '';
    throw err;
  }
};

// 404 → []. Other errors throw — a transient read failure must not look like
// "no prior history" or the next upload would erase every applied record.
export const loadSuggestionsFromFileset = async (
  workspace: string,
  signal?: AbortSignal
): Promise<OptimizationSuggestion[]> => {
  try {
    const blob = await filesDownloadFile(workspace, OPTIMIZER_FILESET, SUGGESTIONS_PATH, signal);
    if (!blob) return [];
    return parseSuggestions(await blob.text());
  } catch (err) {
    if (isNotFoundError(err)) return [];
    throw err;
  }
};

// Previous-run history: 404 means no run has happened twice yet — UI hides
// the "Previous run" stat card.
export const loadPreviousSuggestionsFromFileset = async (
  workspace: string,
  signal?: AbortSignal
): Promise<OptimizationSuggestion[]> => {
  try {
    const blob = await filesDownloadFile(
      workspace,
      OPTIMIZER_FILESET,
      SUGGESTIONS_PREVIOUS_PATH,
      signal
    );
    if (!blob) return [];
    return parseSuggestions(await blob.text());
  } catch (err) {
    if (isNotFoundError(err)) return [];
    throw err;
  }
};

// Copy-then-overwrite: the platform files API has no rename. Called by run()
// just before uploading new snapshot/suggestions so the prior-run pair lives
// on at *.previous paths until the next run rotates them out.
const copyFile = async (
  workspace: string,
  fromPath: string,
  toPath: string,
  signal: AbortSignal
): Promise<void> => {
  let blob: Blob | null = null;
  try {
    blob = await filesDownloadFile(workspace, OPTIMIZER_FILESET, fromPath, signal);
  } catch (err) {
    if (isNotFoundError(err)) return;
    throw err;
  }
  if (!blob) return;
  await filesUploadFile(workspace, OPTIMIZER_FILESET, toPath, blob, signal);
};

export const archivePreviousRun = async (workspace: string, signal: AbortSignal): Promise<void> => {
  await Promise.all([
    copyFile(workspace, SNAPSHOT_PATH, SNAPSHOT_PREVIOUS_PATH, signal),
    copyFile(workspace, SUGGESTIONS_PATH, SUGGESTIONS_PREVIOUS_PATH, signal),
  ]);
};

// 404 → null. Other errors throw to avoid spurious new_model_scan floods.
export const loadSnapshot = async (
  workspace: string,
  signal?: AbortSignal
): Promise<SnapshotShape | null> => {
  try {
    const blob = await filesDownloadFile(workspace, OPTIMIZER_FILESET, SNAPSHOT_PATH, signal);
    if (!blob) return null;
    return JSON.parse(await blob.text()) as SnapshotShape;
  } catch (err) {
    if (isNotFoundError(err)) return null;
    throw err;
  }
};

// First upload after the fileset is deleted/never-existed fails; create then
// retry. Create may 409 if a parallel uploader already made it — fine.
export const uploadToFileset = async (
  workspace: string,
  path: string,
  content: string,
  signal: AbortSignal
): Promise<void> => {
  const blob = new Blob([content], { type: 'application/octet-stream' });
  try {
    await filesUploadFile(workspace, OPTIMIZER_FILESET, path, blob, signal);
    return;
  } catch (err) {
    if (isCanceledError(err)) throw err;
  }
  try {
    await filesCreateFileset(workspace, { name: OPTIMIZER_FILESET }, signal);
  } catch (err) {
    if (isCanceledError(err)) throw err;
  }
  await filesUploadFile(workspace, OPTIMIZER_FILESET, path, blob, signal);
};

// Ensure the named fileset exists and contains the bundled sample eval config.
// Idempotent: existing files are left untouched (the fileset may have been
// customized by the user). Failures here surface as the apply step failing —
// the agent + deployment are already in place at that point.
export const ensureEvalConfigFileset = async (
  workspace: string,
  fileset: string,
  signal: AbortSignal
): Promise<void> => {
  let existingPaths = new Set<string>();
  try {
    const listing = await filesListFilesetFiles(workspace, fileset, undefined, signal);
    existingPaths = new Set((listing?.data ?? []).map((f) => f.path));
  } catch (err) {
    if (isCanceledError(err)) throw err;
    if (!isNotFoundError(err)) throw err;
    try {
      await filesCreateFileset(workspace, { name: fileset }, signal);
    } catch (createErr) {
      if (isCanceledError(createErr)) throw createErr;
      // 409 is fine — a parallel apply already created it.
    }
  }
  const uploads: Array<{ path: string; content: string; type: string }> = [];
  if (!existingPaths.has(SAMPLE_EVAL_CONFIG_PATH)) {
    uploads.push({
      path: SAMPLE_EVAL_CONFIG_PATH,
      content: SAMPLE_EVAL_YAML,
      type: 'application/yaml',
    });
  }
  if (!existingPaths.has(SAMPLE_EVAL_DATA_PATH)) {
    uploads.push({
      path: SAMPLE_EVAL_DATA_PATH,
      content: SAMPLE_EVAL_DATA_JSON,
      type: 'application/json',
    });
  }
  for (const u of uploads) {
    const blob = new Blob([u.content], { type: u.type });
    await filesUploadFile(workspace, fileset, u.path, blob, signal);
  }
};

const ALLOWED_APPLY_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

interface ApplyContext {
  workspace: string;
  suggestion: OptimizationSuggestion;
  // Names declared by POST /agents steps earlier in the same apply; a later
  // POST /deployments may target one of these (sibling pattern).
  declaredAgentNames: Set<string>;
}

// Each rule binds identity to suggestion.agent or names declared earlier in the
// same apply, since the fileset is multi-writer. bindIdentity returns null if
// allowed or an error message. PATCH /agents is omitted — Agents v2 only
// implements POST/GET/LIST/DELETE; model swaps go through create-sibling.
interface ApplyRule {
  method: SuggestionApplyMethod;
  pattern: RegExp;
  bindIdentity: (resolved: URL, body: unknown, ctx: ApplyContext) => string | null;
}

const APPLY_ALLOWLIST: ReadonlyArray<ApplyRule> = [
  // Create sibling agent. Record body.name so a later POST /deployments can
  // target it.
  {
    method: 'POST',
    pattern: /^\/apis\/agents\/v2\/workspaces\/[^/]+\/agents\/?$/,
    bindIdentity: (_url, body, ctx) => {
      if (typeof body !== 'object' || body === null) return 'body must be an object';
      const name = (body as { name?: unknown }).name;
      if (typeof name !== 'string' || name.length === 0) {
        return 'body.name must be a non-empty string';
      }
      ctx.declaredAgentNames.add(name);
      return null;
    },
  },
  // Create deployment for suggestion.agent or a sibling declared earlier.
  {
    method: 'POST',
    pattern: /^\/apis\/agents\/v2\/workspaces\/[^/]+\/deployments\/?$/,
    bindIdentity: (_url, body, ctx) => {
      if (typeof body !== 'object' || body === null) return 'body must be an object';
      const agent = (body as { agent?: unknown }).agent;
      if (typeof agent !== 'string' || agent.length === 0) {
        return 'body.agent must be a non-empty string';
      }
      const allowed = agent === ctx.suggestion.agent || ctx.declaredAgentNames.has(agent);
      if (!allowed) {
        return `body.agent "${agent}" is not suggestion.agent ("${
          ctx.suggestion.agent ?? '<unset>'
        }") or a sibling declared by a prior POST /agents step`;
      }
      return null;
    },
  },
  // Submit an evaluate-agent platform job against suggestion.agent or a
  // sibling declared earlier. Rejects `agent` values containing `://` so the
  // job can't be pointed at an arbitrary HTTP endpoint, and rejects
  // `workspace/name` refs whose workspace differs from the apply context.
  {
    method: 'POST',
    pattern: /^\/apis\/agents\/v2\/workspaces\/[^/]+\/jobs\/evaluate\/?$/,
    bindIdentity: (_url, body, ctx) => {
      if (typeof body !== 'object' || body === null) return 'body must be an object';
      const spec = (body as { spec?: unknown }).spec;
      if (typeof spec !== 'object' || spec === null) return 'body.spec must be an object';
      const agent = (spec as { agent?: unknown }).agent;
      if (typeof agent !== 'string' || agent.length === 0) {
        return 'body.spec.agent must be a non-empty string';
      }
      if (agent.includes('://')) {
        return 'body.spec.agent must be a platform agent ref, not an endpoint URL';
      }
      let bareName: string;
      if (agent.includes('/')) {
        const [ws, name] = agent.split('/', 2);
        if (ws !== ctx.workspace) {
          return `body.spec.agent workspace "${ws}" must match apply workspace "${ctx.workspace}"`;
        }
        bareName = name;
      } else {
        bareName = agent;
      }
      const allowed = bareName === ctx.suggestion.agent || ctx.declaredAgentNames.has(bareName);
      if (!allowed) {
        return `body.spec.agent "${agent}" is not suggestion.agent ("${
          ctx.suggestion.agent ?? '<unset>'
        }") or a sibling declared by a prior POST /agents step`;
      }
      return null;
    },
  },
];

const extractWorkspaceSegment = (pathname: string): string | undefined => {
  const m = /^\/apis\/[^/]+\/v\d+\/workspaces\/([^/]+)/.exec(pathname);
  return m ? decodeURIComponent(m[1]) : undefined;
};

// JSONL is multi-writer / untrusted. Validates method, path shape, origin,
// workspace, and an APPLY_ALLOWLIST rule whose identity binding holds. Stop-gap
// until server-side signed action IDs.
const validateApplySpec = (apply: SuggestionApplySpec, ctx: ApplyContext): string => {
  if (!ALLOWED_APPLY_METHODS.has(apply.method)) {
    throw new Error(`Apply rejected: method "${apply.method}" not allowed`);
  }
  const path = apply.path;
  if (typeof path !== 'string' || path.length === 0) {
    throw new Error('Apply rejected: path missing');
  }
  if (!path.startsWith('/') || path.startsWith('//')) {
    throw new Error('Apply rejected: path must be a same-origin absolute path (start with `/`)');
  }
  if (path.includes('://')) {
    throw new Error('Apply rejected: path must not contain a scheme');
  }
  // Allowlist matches on pathname only; reject query/fragment so a planted
  // `?force=true` can't ride along.
  if (path.includes('?') || path.includes('#')) {
    throw new Error('Apply rejected: path must not contain a query string or fragment');
  }
  // eslint-disable-next-line no-control-regex
  if (/[\x00-\x1f\x7f]/.test(path)) {
    throw new Error('Apply rejected: path contains control characters');
  }
  if (!PLATFORM_BASE_URL) {
    throw new Error('Apply rejected: Platform API URL is not configured');
  }
  let resolved: URL;
  let baseOrigin: string;
  try {
    baseOrigin = new URL(PLATFORM_BASE_URL).origin;
    resolved = new URL(path, PLATFORM_BASE_URL);
  } catch {
    throw new Error('Apply rejected: could not resolve URL');
  }
  if (resolved.origin !== baseOrigin) {
    throw new Error(`Apply rejected: origin mismatch (resolved ${resolved.origin})`);
  }
  const ws = extractWorkspaceSegment(resolved.pathname);
  if (!ws) {
    throw new Error('Apply rejected: not a workspace-scoped Platform API path');
  }
  if (ws !== ctx.workspace) {
    throw new Error(
      `Apply rejected: workspace mismatch (path targets "${ws}", current "${ctx.workspace}")`
    );
  }
  const rule = APPLY_ALLOWLIST.find(
    (r) => r.method === apply.method && r.pattern.test(resolved.pathname)
  );
  if (!rule) {
    throw new Error(
      `Apply rejected: ${apply.method} ${resolved.pathname} is not an allowlisted optimizer action`
    );
  }
  const bindError = rule.bindIdentity(resolved, apply.body, ctx);
  if (bindError) {
    throw new Error(`Apply rejected: ${bindError}`);
  }
  return path;
};

// Runs steps sequentially. Stops on first failure (no rollback). Returns the
// created deployment + evaluation-job names so callers can poll readiness /
// results after the apply array completes.
export const applySuggestion = async (
  suggestion: OptimizationSuggestion,
  workspace: string,
  signal?: AbortSignal
): Promise<ApplyResult> => {
  const apply = suggestion.apply;
  const steps = Array.isArray(apply) ? apply : apply ? [apply] : [];
  if (steps.length === 0) {
    throw new Error('Apply rejected: no steps');
  }
  const ctx: ApplyContext = { workspace, suggestion, declaredAgentNames: new Set() };
  const deploymentNames: string[] = [];
  const evalJobNames: string[] = [];
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    let safePath: string;
    try {
      safePath = validateApplySpec(step, ctx);
    } catch (err) {
      throw new Error(`Step ${i + 1}/${steps.length}: ${toError(err).message}`);
    }
    const response = await customFetch<{ name?: string } | undefined>({
      url: safePath,
      method: step.method,
      data: step.body,
      headers: { 'Content-Type': 'application/json' },
      signal,
    });
    if (step.method === 'POST' && response?.name) {
      if (/\/deployments(?:\/|$|\?)/.test(safePath)) {
        deploymentNames.push(response.name);
      } else if (/\/jobs\/evaluate(?:\/|$|\?)/.test(safePath)) {
        evalJobNames.push(response.name);
      }
    }
  }
  return { deploymentNames, evalJobNames };
};

interface DeploymentListing {
  name: string;
  agent: string;
  status?: string;
}

export const fetchDeploymentCounts = async (
  workspace: string,
  signal: AbortSignal
): Promise<Record<string, number>> => {
  const counts: Record<string, number> = {};
  let page = 1;
  try {
    while (true) {
      const res = await customFetch<{ data?: DeploymentListing[] }>({
        url: `/apis/agents/v2/workspaces/${encodeURIComponent(workspace)}/deployments`,
        method: 'GET',
        params: { page, page_size: DEPLOYMENTS_PAGE_SIZE },
        signal,
      });
      const batch = res?.data ?? [];
      for (const d of batch) {
        counts[d.agent] = (counts[d.agent] ?? 0) + 1;
      }
      if (batch.length < DEPLOYMENTS_PAGE_SIZE) break;
      page++;
    }
    return counts;
  } catch (err) {
    if (isCanceledError(err)) throw err;
    return counts;
  }
};

interface DeploymentStatusResponse {
  name: string;
  status?: string;
  error?: string;
  endpoint?: string;
}

// Mirrors TERMINAL_DEPLOYMENT_STATUSES in AgentsDataView.
const TERMINAL_FAILURE_STATUSES = new Set(['failed', 'error', 'stopped']);

const waitForDeployment = async (
  workspace: string,
  name: string,
  opts: { timeoutMs: number; intervalMs: number; signal: AbortSignal }
): Promise<void> => {
  const url = `/apis/agents/v2/workspaces/${encodeURIComponent(workspace)}/deployments/${encodeURIComponent(name)}`;
  const start = Date.now();
  while (Date.now() - start < opts.timeoutMs) {
    if (opts.signal.aborted) throw new DOMException(`Wait for "${name}" aborted`, 'AbortError');
    const dep = await customFetch<DeploymentStatusResponse>({
      url,
      method: 'GET',
      signal: opts.signal,
    });
    const status = dep?.status ?? '';
    if (status === 'running') return;
    if (TERMINAL_FAILURE_STATUSES.has(status)) {
      throw new Error(`Deployment "${name}" ${status}${dep?.error ? `: ${dep.error}` : ''}`);
    }
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(resolve, opts.intervalMs);
      opts.signal.addEventListener(
        'abort',
        () => {
          clearTimeout(t);
          reject(new DOMException(`Wait for "${name}" aborted`, 'AbortError'));
        },
        { once: true }
      );
    });
  }
  throw new Error(`Timed out waiting for deployment "${name}" to become running`);
};

export const waitForDeployments = async (
  workspace: string,
  names: string[],
  opts: WaitForDeploymentsOptions
): Promise<void> => {
  if (names.length === 0) return;
  const timeoutMs = opts.timeoutMs ?? 5 * 60 * 1000;
  const intervalMs = opts.intervalMs ?? 2000;
  await Promise.all(
    names.map((name) =>
      waitForDeployment(workspace, name, { timeoutMs, intervalMs, signal: opts.signal })
    )
  );
};

// ---------------------------------------------------------------------------
// Eval-job polling + score helpers
// ---------------------------------------------------------------------------

interface RawJobStatus {
  name?: string;
  status?: string;
  error_details?: { message?: string } | null;
  status_details?: { message?: string } | null;
}

const NON_TERMINAL_EVAL_STATUSES = new Set(['created', 'pending', 'queued', 'running']);
const FAILURE_EVAL_STATUSES = new Set(['failed', 'cancelled', 'canceled', 'error']);
const SUCCESS_EVAL_STATUSES = new Set(['completed', 'succeeded', 'success']);

const normaliseEvalStatus = (raw: string): EvalJobStatus => {
  const v = raw.toLowerCase();
  if (SUCCESS_EVAL_STATUSES.has(v)) return 'completed';
  if (FAILURE_EVAL_STATUSES.has(v))
    return v === 'cancelled' || v === 'canceled' ? 'cancelled' : 'failed';
  if (v === 'running') return 'running';
  if (NON_TERMINAL_EVAL_STATUSES.has(v)) return 'queued';
  return 'unknown';
};

export const fetchEvalJobStatus = async (
  workspace: string,
  name: string,
  signal: AbortSignal
): Promise<EvalJobStatusResponse> => {
  const res = await customFetch<RawJobStatus>({
    url: `/apis/agents/v2/workspaces/${encodeURIComponent(workspace)}/jobs/evaluate/${encodeURIComponent(name)}/status`,
    method: 'GET',
    signal,
  });
  const status = normaliseEvalStatus(res?.status ?? '');
  const error = res?.error_details?.message ?? res?.status_details?.message;
  return { name, status, error: error ?? undefined };
};

export const waitForEvalJob = async (
  workspace: string,
  name: string,
  opts: WaitForEvalJobOptions
): Promise<EvalJobStatusResponse> => {
  const timeoutMs = opts.timeoutMs ?? 30 * 60 * 1000;
  const intervalMs = opts.intervalMs ?? 5000;
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (opts.signal.aborted) {
      throw new DOMException(`Wait for eval "${name}" aborted`, 'AbortError');
    }
    const job = await fetchEvalJobStatus(workspace, name, opts.signal);
    if (job.status === 'completed') return job;
    if (job.status === 'failed' || job.status === 'cancelled') {
      throw new Error(`Evaluation "${name}" ${job.status}${job.error ? `: ${job.error}` : ''}`);
    }
    if (opts.onStatus) opts.onStatus(job.status);
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(resolve, intervalMs);
      opts.signal.addEventListener(
        'abort',
        () => {
          clearTimeout(t);
          reject(new DOMException(`Wait for eval "${name}" aborted`, 'AbortError'));
        },
        { once: true }
      );
    });
  }
  throw new Error(`Timed out waiting for evaluation "${name}" to complete`);
};

// nat-eval writes outputs under the YAML's ``output_dir`` so the file
// path may be nested (e.g. ``eval/agent/accuracy_output.json``); we match
// on the basename rather than the full path.
const EVALUATOR_OUTPUT_BASENAME_RE = /^([^/]+)_output\.json$/;
const NON_EVALUATOR_BASENAMES = new Set(['workflow_output.json', 'workflow_output_atif.json']);

const basenameOf = (path: string): string => path.split('/').pop() ?? path;

const matchEvaluatorBasename = (path: string): string | null => {
  const base = basenameOf(path);
  if (NON_EVALUATOR_BASENAMES.has(base)) return null;
  const m = EVALUATOR_OUTPUT_BASENAME_RE.exec(base);
  return m ? m[1] : null;
};

// Reads every ``<evaluator>_output.json`` in the eval output fileset and
// returns the average_score from each. nat-eval names files after the YAML
// evaluator key (``accuracy`` → ``accuracy_output.json``); ``workflow_output``
// files are NOT evaluator results and are skipped.
export const fetchEvalAverageScores = async (
  workspace: string,
  outputFileset: string,
  signal: AbortSignal
): Promise<EvalScore[]> => {
  let listing;
  try {
    listing = await filesListFilesetFiles(workspace, outputFileset, undefined, signal);
  } catch (err) {
    if (isCanceledError(err)) throw err;
    if (isNotFoundError(err)) return [];
    throw err;
  }
  const candidates = (listing?.data ?? [])
    .map((f) => ({ file: f, evaluator: matchEvaluatorBasename(f.path) }))
    .filter((entry): entry is { file: typeof entry.file; evaluator: string } => !!entry.evaluator);
  const scores: EvalScore[] = [];
  for (const { file, evaluator } of candidates) {
    try {
      const blob = await filesDownloadFile(workspace, outputFileset, file.path, signal);
      if (!blob) continue;
      const text = await blob.text();
      const parsed = JSON.parse(text) as { average_score?: unknown };
      const score = parsed.average_score;
      if (typeof score === 'number' && Number.isFinite(score)) {
        scores.push({ evaluator, averageScore: score });
      }
    } catch (err) {
      if (isCanceledError(err)) throw err;
      // A single malformed evaluator file shouldn't drop scores from the others.
    }
  }
  return scores;
};

export const markSuggestionAppliedInFileset = async (
  workspace: string,
  target: OptimizationSuggestion,
  signal: AbortSignal
): Promise<void> => {
  const current = await loadSuggestionsFromFileset(workspace, signal);
  const targetIdentity = suggestionIdentity(target);
  let mutated = false;
  const next = current.map((s) => {
    if (s.applied || suggestionIdentity(s) !== targetIdentity) return s;
    mutated = true;
    return { ...s, applied: true, applied_at: new Date().toISOString() };
  });
  if (!mutated) return;
  await uploadToFileset(workspace, SUGGESTIONS_PATH, serializeSuggestions(next), signal);
};

// Works with content-safety / safety-guard models and plain self-check rails.
const buildSafetyPrompt = (sample: string): string =>
  `Task: Check if the content below complies with safety policy. The content should not contain harmful, hateful, violent, sexual, illegal, or PII material.

Content:
"""
${sample}
"""

Should this content be blocked? Answer with only "Yes" or "No".`;

// Returns false on non-cancel errors so a missing safety verdict doesn't block
// the rest of the analysis. Cancels propagate.
export const checkContentSafety = async (
  workspace: string,
  modelName: string,
  sampleText: string,
  signal: AbortSignal
): Promise<boolean> => {
  if (!sampleText) return false;
  try {
    const sample = sampleText.slice(0, CONTENT_SAFETY_SAMPLE_CHARS);
    const res = await customFetch<{ choices?: { message?: { content?: string } }[] }>({
      url: `/apis/inference-gateway/v2/workspaces/${encodeURIComponent(workspace)}/openai/-/v1/chat/completions`,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      data: {
        model: modelName,
        messages: [{ role: 'user', content: buildSafetyPrompt(sample) }],
        max_tokens: 8,
        temperature: 0,
      },
      signal,
    });
    const content = (res?.choices?.[0]?.message?.content ?? '').trim().toLowerCase();
    return content.startsWith('yes') || /unsafe|blocked|violation|harmful/i.test(content);
  } catch (err) {
    if (isCanceledError(err)) throw err;
    return false;
  }
};
