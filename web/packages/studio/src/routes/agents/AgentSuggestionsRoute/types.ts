// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ModelEntity } from '@nemo/sdk/generated/platform/schema/ModelEntity';
import type { AgentConfig } from '@studio/components/dataViews/AgentsDataView';

export type SuggestionApplyMethod = 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export interface SuggestionApplySpec {
  method: SuggestionApplyMethod;
  /** Same-origin absolute path; re-validated in applySuggestion. */
  path: string;
  body?: Record<string, unknown>;
}

/**
 * Eval-job pointers persisted to the suggestions JSONL so the tile's eval row
 * survives a reload/navigation: on load the hook re-seeds ``evalStates`` from
 * this and re-polls the jobs to completion. Only job names + agent names are
 * stored — scores/profiler are re-fetched, and output filesets / detail hrefs
 * are derived from the agent names.
 */
export interface PersistedEvalRun {
  /** Tuned ("after") eval job name. */
  jobName: string;
  /** Sibling agent the tuned eval scored — drives the output-fileset lookup. */
  siblingAgentName: string;
  /** Baseline ("before") run against the original agent + its job name, when a
   *  comparison run was submitted. Absent/null when no baseline ran. */
  baseline?: { agentName: string; jobName: string } | null;
}

export interface OptimizationSuggestion {
  type: string;
  title: string;
  detail: string;
  agent?: string;
  model?: string;
  severity?: string;
  suggested_actions?: string[];
  apply?: SuggestionApplySpec | SuggestionApplySpec[];
  /** Short note above the Apply button — what pressing Apply does. */
  apply_description?: string;
  /** Persisted to JSONL so applied state survives reloads. */
  applied?: boolean;
  applied_at?: string;
  /** Persisted eval-job pointers so the eval row re-hydrates after a reload. */
  eval_run?: PersistedEvalRun;
}

/**
 * Context passed alongside a tile's Apply click when the click is really a
 * "re-run just the evaluation" retry: the optimization already succeeded and
 * deployed a tuned sibling, only the eval failed. Carries the deployed sibling
 * so the orchestrated apply can skip the (expensive) sweep + redeploy.
 */
export interface EvalRetryContext {
  /** The already-deployed tuned sibling from the prior successful sweep. */
  siblingAgentName: string;
}

export interface SuggestionTileProps {
  suggestion: OptimizationSuggestion;
  onApply?: (suggestion: OptimizationSuggestion, opts?: { evalRetry?: EvalRetryContext }) => void;
  isApplying?: boolean;
  isApplied?: boolean;
  applyError?: string | null;
  evalState?: EvalUiState | null;
}

export interface AgentListing {
  name: string;
  config?: AgentConfig;
}

export interface SnapshotPerAgent {
  modelNames: string[];
  agentNames: string[];
  updatedAt: string;
}

export interface SnapshotShape {
  agents: Record<string, SnapshotPerAgent>;
}

export interface AnalyzeInput {
  agents: AgentListing[];
  models: ModelEntity[];
  piiSampleText: string;
  contentSafetyRisk: boolean;
  prevSnapshot: SnapshotShape | null;
  /** Required to construct workspace-scoped apply paths. */
  workspace: string;
}

export interface ApplyResult {
  deploymentNames: string[];
  evalJobNames: string[];
}

export interface WaitForDeploymentsOptions {
  /** Default: 5 minutes. */
  timeoutMs?: number;
  /** Default: 2s. */
  intervalMs?: number;
  signal: AbortSignal;
}

/**
 * Lifecycle of a suggestion's one-click apply, surfaced as a colored badge on
 * the tile. `applying` covers resource creation + deployment-readiness wait;
 * `success`/`failed` are the terminal states (green/red). Derived from the
 * apply flags via ``applyStatusOf`` — ``failed`` wins over ``success`` so a
 * "resources created but deployment never went ready" case reads as failed.
 */
export type ApplyStatus = 'applying' | 'success' | 'failed';

export type EvalJobStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'unknown';

export interface EvalJobStatusResponse {
  name: string;
  status: EvalJobStatus;
  /** Best-effort error message when status is failed/cancelled. */
  error?: string;
}

export interface WaitForEvalJobOptions {
  /** Default: 30 minutes — `nat eval` runs can take a while. */
  timeoutMs?: number;
  /** Default: 5s. */
  intervalMs?: number;
  signal: AbortSignal;
  /** Called on each poll so the UI can surface progress without flicker. */
  onStatus?: (status: EvalJobStatus) => void;
}

export interface EvalScore {
  evaluator: string;
  averageScore: number;
}

/**
 * Token/latency aggregates parsed from the NAT profiler artifacts in an eval
 * output fileset. Latency/runtime come from ``inference_optimization.json``;
 * token averages are aggregated from ``standardized_data_all.csv``. Every field
 * is nullable so a run without the profiler plugin (or a partially-written
 * output) degrades to "—" rather than failing the comparison.
 */
export interface ProfilerStats {
  /** Mean total tokens per evaluated dataset item. */
  avgTotalTokens: number | null;
  /** Mean prompt tokens per evaluated dataset item. */
  avgPromptTokens: number | null;
  /** Mean completion tokens per evaluated dataset item. */
  avgCompletionTokens: number | null;
  /** p95 of per-LLM-call latency, in seconds. */
  llmLatencyP95Seconds: number | null;
  /** p95 end-to-end workflow runtime, in seconds. */
  workflowRuntimeP95Seconds: number | null;
}

/**
 * A single evaluation run's outcome — used for both the baseline (original
 * agent, "before") and the optimized (sibling agent, "after") sides of the
 * comparison view.
 */
export interface EvalRunResult {
  /** Agent this run scored — original for baseline, sibling for optimized. */
  agentName: string;
  jobName: string;
  status: EvalJobStatus;
  /** Per-evaluator average scores; populated after the job completes. */
  scores: EvalScore[];
  /** Token/latency aggregates; null until parsed (or when unavailable). */
  profiler: ProfilerStats | null;
  error?: string;
}

export interface EvalUiState {
  /** Platform job name returned by the apply's ``POST /jobs/evaluate`` step. */
  jobName: string;
  /** Sibling agent the eval ran against (drives ``<sibling>-eval-out`` lookup). */
  siblingAgentName: string;
  status: EvalJobStatus;
  /** Per-evaluator average scores; populated after job completes. */
  scores: EvalScore[];
  error?: string;
  detailHref: string;
  /** Token/latency aggregates for the optimized ("after") run. */
  profiler?: ProfilerStats | null;
  /**
   * Baseline ("before") run against the original agent. Present only when the
   * optimizer-comparison flag is on and a model_optimization suggestion is
   * applied; drives the side-by-side comparison view.
   */
  baseline?: EvalRunResult | null;
}

export type OptimizerPhase = 'idle' | 'running' | 'done' | 'failed';

export interface RunState {
  phase: OptimizerPhase;
  step: string;
  error: Error | null;
}

export interface EvalConfigChoice {
  /** When ``null`` the optimizer apply flow seeds the bundled sample into the
   *  per-agent eval fileset (current default behaviour). When set, seeding
   *  is skipped and the apply spec's eval step is patched to point at the
   *  user-chosen fileset + path directly. */
  filesetOverride: { fileset: string; configPath: string } | null;
}
