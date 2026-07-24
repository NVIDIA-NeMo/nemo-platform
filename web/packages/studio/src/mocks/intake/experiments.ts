// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  EvaluationResponse,
  EvaluationResponsesPage,
  EvaluationSessionResponse,
  EvaluationSessionResponsesPage,
  ExperimentGroupResponse,
} from '@nemo/sdk/generated/platform/schema';

const WORKSPACE = 'default';

/** The experiment group the EvaluationSessionDetailRoute tests navigate under. */
export const mockExperimentGroup = (name: string): ExperimentGroupResponse => ({
  id: `grp_${name}`,
  name,
  workspace: WORKSPACE,
  description: '',
  default_sort: 'started_at',
  evaluation_count: 2,
  experiment_count: 2,
});

/** Evaluation names that live in the mock group (each fans out one runs query). */
export const MOCK_EVALUATION_NAMES = ['my-experiment', 'my-experiment-v2'] as const;

const mockEvaluation = (name: string): EvaluationResponse => ({
  id: `eval_${name}`,
  name,
  workspace: WORKSPACE,
  experiment_ids: ['grp_my-group'],
  dataset_name: 'sample-dataset',
  // Deprecated readonly aliases the generated type still requires.
  parent_experiment_id: '',
  experiment_group_id: 'grp_my-group',
});

export const mockEvaluationsPage = (): EvaluationResponsesPage => ({
  data: MOCK_EVALUATION_NAMES.map(mockEvaluation),
});

const mockRun = (
  evaluationName: string,
  sessionId: string,
  testCaseId: string
): EvaluationSessionResponse => ({
  workspace: WORKSPACE,
  evaluation_name: evaluationName,
  experiment_name: evaluationName,
  session_id: sessionId,
  test_case_id: testCaseId,
  trace_id: `trace-${sessionId}`,
  root_span_id: `${sessionId}-root`,
  started_at: '2026-01-01T00:00:00Z',
  status: 'success',
});

// Runs of a test case, keyed by evaluation name. The primary session
// `session-agent-run-001` lives in `my-experiment` alongside a sibling run, and
// `my-experiment-v2` contributes a third run — so the compare selector has options.
const RUNS_BY_EVALUATION: Record<string, (testCaseId: string) => EvaluationSessionResponse[]> = {
  'my-experiment': (testCaseId) => [
    mockRun('my-experiment', 'session-agent-run-001', testCaseId),
    mockRun('my-experiment', 'session-agent-run-002', testCaseId),
  ],
  'my-experiment-v2': (testCaseId) => [
    mockRun('my-experiment-v2', 'session-agent-run-101', testCaseId),
  ],
};

export const mockEvaluationSessionsPage = (
  evaluationName: string,
  testCaseId: string | null
): EvaluationSessionResponsesPage => ({
  data: testCaseId ? (RUNS_BY_EVALUATION[evaluationName]?.(testCaseId) ?? []) : [],
});
