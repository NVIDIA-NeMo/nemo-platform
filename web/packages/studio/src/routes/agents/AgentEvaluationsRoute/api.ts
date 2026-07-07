// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { customFetch } from '@nemo/sdk/generated/fetchers/platform';
import { filesDownloadFile, filesListFilesetFiles } from '@nemo/sdk/generated/platform/api';

const PAGE_SIZE = 50;

// ---------------------------------------------------------------------------
// Job status
// ---------------------------------------------------------------------------

const TERMINAL_STATUSES = new Set([
  'completed',
  'succeeded',
  'success',
  'failed',
  'cancelled',
  'canceled',
  'error',
]);

/** A job is terminal once it has finished running (whether it succeeded,
 *  failed, or was cancelled). Scores and other output-fileset artifacts only
 *  exist for terminal jobs. */
export const isTerminalStatus = (status: string | undefined | null): boolean =>
  TERMINAL_STATUSES.has((status ?? '').toLowerCase());

// ---------------------------------------------------------------------------
// Job listing + retrieval
// ---------------------------------------------------------------------------

export interface AgentEvalJobSpec {
  agent?: string | null;
  eval_config?: string;
  eval_config_fileset?: string | null;
  output?: string | null;
  workspace?: string;
}

export interface AgentEvalJob {
  name: string;
  description?: string | null;
  workspace: string;
  status: string;
  created_at: string;
  updated_at: string;
  spec: AgentEvalJobSpec;
  status_details?: { message?: string } | null;
  error_details?: { message?: string } | null;
}

interface PaginatedJobsResponse {
  data?: AgentEvalJob[];
  pagination?: { total?: number; page?: number; page_size?: number };
}

const evalJobsBasePath = (workspace: string): string =>
  `/apis/agents/v2/workspaces/${encodeURIComponent(workspace)}/jobs/evaluate`;

const evalJobPath = (workspace: string, name: string): string =>
  `${evalJobsBasePath(workspace)}/${encodeURIComponent(name)}`;

export const fetchAgentEvalJobs = async (
  workspace: string,
  signal: AbortSignal
): Promise<AgentEvalJob[]> => {
  const all: AgentEvalJob[] = [];
  let page = 1;
  while (true) {
    const res = await customFetch<PaginatedJobsResponse>({
      url: evalJobsBasePath(workspace),
      method: 'GET',
      params: { page, page_size: PAGE_SIZE, sort: '-created_at' },
      signal,
    });
    const batch = res?.data ?? [];
    all.push(...batch);
    if (batch.length < PAGE_SIZE) break;
    page++;
  }
  return all;
};

export const fetchAgentEvalJob = async (
  workspace: string,
  name: string,
  signal: AbortSignal
): Promise<AgentEvalJob | null> => {
  try {
    const res = await customFetch<AgentEvalJob | undefined>({
      url: evalJobPath(workspace, name),
      method: 'GET',
      signal,
    });
    return res ?? null;
  } catch (err) {
    const e = err as { response?: { status?: number }; status?: number };
    if (e?.response?.status === 404 || e?.status === 404) return null;
    throw err;
  }
};

export const cancelAgentEvalJob = async (
  workspace: string,
  name: string,
  signal: AbortSignal
): Promise<void> => {
  await customFetch({
    url: `${evalJobPath(workspace, name)}/cancel`,
    method: 'POST',
    signal,
  });
};

// ---------------------------------------------------------------------------
// Output fileset (eval results)
// ---------------------------------------------------------------------------

export interface AgentEvalOutputFile {
  path: string;
  size?: number;
}

export const fetchAgentEvalOutputFiles = async (
  workspace: string,
  outputFileset: string,
  signal: AbortSignal
): Promise<AgentEvalOutputFile[]> => {
  try {
    const listing = await filesListFilesetFiles(workspace, outputFileset, undefined, signal);
    return (listing?.data ?? []).map((f) => ({ path: f.path, size: f.size ?? undefined }));
  } catch (err) {
    const e = err as { response?: { status?: number }; status?: number };
    if (e?.response?.status === 404 || e?.status === 404) return [];
    throw err;
  }
};

export const downloadAgentEvalOutputFile = async (
  workspace: string,
  outputFileset: string,
  remotePath: string,
  signal: AbortSignal
): Promise<Blob | null> => {
  const blob = await filesDownloadFile(workspace, outputFileset, remotePath, signal);
  return blob ?? null;
};

// ---------------------------------------------------------------------------
// Parsed eval result shapes
// ---------------------------------------------------------------------------

export interface EvalScoreBreakdown {
  /** ``coverage_score`` / ``correctness_score`` / ``relevance_score`` etc. */
  [key: string]: number;
}

export interface EvaluatorOutputItem {
  id: string | number;
  score: number | null;
  /** nat-eval ``tunable_rag_evaluator`` writes a structured object; other
   *  evaluators write a plain string. Render whichever is present. */
  reasoning:
    | string
    | {
        question?: string;
        answer_description?: string;
        generated_answer?: string;
        score_breakdown?: EvalScoreBreakdown;
        reasoning?: string;
      };
  error: string | null;
}

export interface EvaluatorOutput {
  evaluator: string;
  averageScore: number | null;
  items: EvaluatorOutputItem[];
}

export interface WorkflowOutputItem {
  id: string | number;
  question: string;
  answer: string;
  generated_answer: string | null;
  intermediate_steps?: unknown[];
  expected_intermediate_steps?: unknown[];
}

const downloadJson = async <T>(
  workspace: string,
  fileset: string,
  remotePath: string,
  signal: AbortSignal
): Promise<T | null> => {
  const blob = await filesDownloadFile(workspace, fileset, remotePath, signal);
  if (!blob) return null;
  return JSON.parse(await blob.text()) as T;
};

const EVALUATOR_OUTPUT_BASENAME_RE = /^([^/]+)_output\.json$/;
const NON_EVALUATOR_BASENAMES = new Set(['workflow_output.json', 'workflow_output_atif.json']);
const WORKFLOW_OUTPUT_BASENAMES = new Set(['workflow_output.json']);
const CONFIG_BASENAMES = new Set([
  'config_original.yml',
  'config_effective.yml',
  'config_metadata.json',
]);

const basenameOf = (path: string): string => path.split('/').pop() ?? path;

/** Reads every ``<evaluator>_output.json`` in the output fileset and parses
 *  the full per-item payload so the detail page can render a table without
 *  forcing the user to download files. Downloads run in parallel via
 *  ``Promise.all`` — they target independent files. */
export const fetchEvaluatorOutputs = async (
  workspace: string,
  outputFileset: string,
  signal: AbortSignal
): Promise<EvaluatorOutput[]> => {
  const files = await fetchAgentEvalOutputFiles(workspace, outputFileset, signal);
  const candidates = files.flatMap((f) => {
    const base = basenameOf(f.path);
    if (NON_EVALUATOR_BASENAMES.has(base)) return [];
    const m = EVALUATOR_OUTPUT_BASENAME_RE.exec(base);
    return m ? [{ file: f, evaluator: m[1] }] : [];
  });
  const settled = await Promise.all(
    candidates.map(async ({ file, evaluator }) => {
      try {
        const parsed = await downloadJson<{
          average_score?: unknown;
          eval_output_items?: EvaluatorOutputItem[];
        }>(workspace, outputFileset, file.path, signal);
        if (!parsed) return null;
        const avg = parsed.average_score;
        return {
          evaluator,
          averageScore: typeof avg === 'number' && Number.isFinite(avg) ? avg : null,
          items: Array.isArray(parsed.eval_output_items) ? parsed.eval_output_items : [],
        } satisfies EvaluatorOutput;
      } catch {
        // Skip malformed evaluator files so one bad one doesn't drop the others.
        return null;
      }
    })
  );
  return settled.filter((s): s is EvaluatorOutput => s !== null);
};

/** Loads ``workflow_output.json`` (the agent's responses to the dataset)
 *  if present in the output fileset. Returns null when not yet written. */
export const fetchWorkflowOutput = async (
  workspace: string,
  outputFileset: string,
  signal: AbortSignal
): Promise<WorkflowOutputItem[] | null> => {
  const files = await fetchAgentEvalOutputFiles(workspace, outputFileset, signal);
  const wf = files.find((f) => WORKFLOW_OUTPUT_BASENAMES.has(basenameOf(f.path)));
  if (!wf) return null;
  try {
    const parsed = await downloadJson<unknown>(workspace, outputFileset, wf.path, signal);
    if (Array.isArray(parsed)) return parsed as WorkflowOutputItem[];
    return null;
  } catch {
    return null;
  }
};

export interface EvalConfigFile {
  /** File basename (e.g. ``config_original.yml``). */
  name: string;
  /** Full path inside the fileset, used for downloads. */
  path: string;
  /** Decoded UTF-8 content of the file. */
  content: string;
  /** ``yaml`` for ``.yml``/``.yaml``, ``json`` otherwise. */
  language: 'yaml' | 'json' | 'text';
}

const detectLanguage = (name: string): EvalConfigFile['language'] => {
  if (name.endsWith('.yml') || name.endsWith('.yaml')) return 'yaml';
  if (name.endsWith('.json')) return 'json';
  return 'text';
};

/** Loads the eval-run config snapshots (``config_original.yml``,
 *  ``config_effective.yml``, ``config_metadata.json``) so the detail page
 *  can render them inline rather than as download-only file rows.
 *  Downloads run in parallel via ``Promise.all`` — independent files. */
export const fetchEvalConfigFiles = async (
  workspace: string,
  outputFileset: string,
  signal: AbortSignal
): Promise<EvalConfigFile[]> => {
  const files = await fetchAgentEvalOutputFiles(workspace, outputFileset, signal);
  const candidates = files.flatMap((f) => {
    const base = basenameOf(f.path);
    return CONFIG_BASENAMES.has(base) ? [{ file: f, name: base }] : [];
  });
  const settled = await Promise.all(
    candidates.map(async ({ file, name }) => {
      try {
        const blob = await filesDownloadFile(workspace, outputFileset, file.path, signal);
        if (!blob) return null;
        return {
          name,
          path: file.path,
          content: await blob.text(),
          language: detectLanguage(name),
        } satisfies EvalConfigFile;
      } catch {
        // Skip unreadable config files individually.
        return null;
      }
    })
  );
  return settled
    .filter((s): s is EvalConfigFile => s !== null)
    .sort((a, b) => a.name.localeCompare(b.name));
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Sibling output fileset name follows the same convention as the optimizer
 * apply path: ``<deployed-agent>-eval-out``. The ``output`` field on the
 * spec carries the literal fileset name when set; older / hand-submitted
 * jobs without ``output`` fall back to a derived guess.
 */
export const outputFilesetForJob = (job: AgentEvalJob): string | null => {
  const explicit = job.spec.output;
  if (typeof explicit === 'string' && explicit.length > 0) {
    return explicit.includes('/') ? (explicit.split('/').pop() ?? null) : explicit;
  }
  const agent = job.spec.agent;
  if (typeof agent === 'string' && agent.length > 0) {
    const bare = agent.includes('/') ? agent.split('/').pop()! : agent;
    return `${bare}-eval-out`;
  }
  return null;
};
