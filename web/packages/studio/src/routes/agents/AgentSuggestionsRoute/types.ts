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
}

export interface EvalRowScore {
  evaluator: string;
  averageScore: number;
}

export interface EvalRowState {
  jobName: string;
  status: EvalJobStatus;
  scores: EvalRowScore[];
  error?: string;
  /** Route to the eval detail page (Phase 2 surface). */
  detailHref: string;
}

export interface SuggestionTileProps {
  suggestion: OptimizationSuggestion;
  onApply?: (suggestion: OptimizationSuggestion) => void;
  isApplying?: boolean;
  isApplied?: boolean;
  applyError?: string | null;
  evalState?: EvalRowState | null;
}

export interface AgentListing {
  name: string;
  config_format?: string;
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
