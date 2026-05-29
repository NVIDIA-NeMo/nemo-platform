// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * POC mock data for the Experiments surface.
 *
 * Mirrors the entity shape from the Experiments technical design (Experiment Group →
 * Candidate → Evaluation Run). Data lives in plain modules for the POC so we don't pull
 * in MSW yet — wire up real Intake endpoints when M1 lands.
 */

export type EvaluatorScore = {
  evaluator_name: string;
  mean: number;
  n_runs: number;
};

export type Candidate = {
  candidate_id: string;
  experiment_group_id: string | null;
  agent_name: string;
  agent_version: string;
  dataset_id: string;
  dataset_version?: string;
  evaluator_scores: EvaluatorScore[];
  run_count: number;
  // Domain metadata shown as configurable columns later. Free-form blob.
  producer_metadata?: Record<string, string | number>;
  // Benchmark fields (only populated when is_benchmark=true)
  is_benchmark: boolean;
  benchmark_slug?: string;
  benchmark_name?: string;
  benchmark_description?: string;
  benchmark_promoted_at?: string;
  benchmark_promoted_via?: 'auto' | 'manual';
  benchmark_promoted_by?: string;
  created_at: string;
  summary?: string;
};

export type ExperimentGroup = {
  experiment_group_id: string;
  name: string;
  description: string;
  goal: string;
  created_at: string;
  summary?: string;
};

// ---------------------------------------------------------------------------
// Datasets that show up in this POC. dataset_id + dataset_version are the keys
// candidates bind to. In the real system these are free-form producer strings.
// ---------------------------------------------------------------------------

export const DATASETS = {
  WIKI_TAG_ACCURACY: { id: 'wiki-tag-accuracy', version: 'v1', name: 'Wiki Tag Accuracy' },
  WIKI_TRAJECTORY: { id: 'wiki-trajectory-judge', version: 'v2', name: 'Wiki Trajectory Judge' },
  DEEP_RESEARCH_QA: { id: 'deep-research-qa', version: 'v1', name: 'Deep Research QA' },
  DEEP_RESEARCH_LATENCY: { id: 'deep-research-latency', version: 'v1', name: 'Deep Research Latency' },
};

// ---------------------------------------------------------------------------
// Experiment Groups
// ---------------------------------------------------------------------------

export const EXPERIMENT_GROUPS: ExperimentGroup[] = [
  {
    experiment_group_id: 'group-deep-research-optimize',
    name: 'Optimize deep research agent',
    description: 'Sweep model + prompt combinations to find a Pareto-frontier candidate for QA accuracy and latency.',
    goal: 'Beat current main on QA accuracy without regressing p95 latency.',
    created_at: '2026-05-26T14:22:00Z',
    summary: 'Three candidates so far. minimax2.7 on Hermes leads on accuracy but with a 2x latency cost.',
  },
  {
    experiment_group_id: 'group-wiki-prompt-tuning',
    name: 'Wiki agent prompt tuning',
    description: 'Iterating on the wiki agent system prompt to improve tag recall without changing the model.',
    goal: 'Push tag recall above 0.6 mean without hurting trajectory quality.',
    created_at: '2026-05-20T09:10:00Z',
  },
  {
    experiment_group_id: 'group-baselines',
    name: 'Main branch baselines',
    description: 'Continually-updated benchmark candidates per (agent, dataset) tuple. New runs land here as main changes.',
    goal: 'Provide stable anchors for all in-flight optimization groups.',
    created_at: '2026-04-30T12:00:00Z',
  },
];

// ---------------------------------------------------------------------------
// Candidates — both regular and benchmark — across the groups above.
// ---------------------------------------------------------------------------

export const CANDIDATES: Candidate[] = [
  // --- Benchmarks (live in the "Main branch baselines" group, but compatibility
  //     is dataset_id + agent_name — group membership is orthogonal) ---
  {
    candidate_id: 'bench-deep-research-main',
    experiment_group_id: 'group-baselines',
    agent_name: 'deep-research-agent',
    agent_version: 'main@a4f1d',
    dataset_id: DATASETS.DEEP_RESEARCH_QA.id,
    dataset_version: DATASETS.DEEP_RESEARCH_QA.version,
    evaluator_scores: [
      { evaluator_name: 'qa_accuracy', mean: 0.681, n_runs: 5 },
      { evaluator_name: 'trajectory_quality', mean: 0.73, n_runs: 5 },
      { evaluator_name: 'cost_usd', mean: 0.041, n_runs: 5 },
    ],
    run_count: 5,
    producer_metadata: { provider: 'nvidia-build' },
    is_benchmark: true,
    benchmark_slug: 'deep-research-main',
    benchmark_name: 'Deep Research — Main',
    benchmark_description: 'Continually-updated baseline of the deep-research agent on the QA dataset. Refreshed nightly from main.',
    benchmark_promoted_at: '2026-05-28T22:00:00Z',
    benchmark_promoted_via: 'auto',
    benchmark_promoted_by: 'nightly-runner',
    created_at: '2026-05-27T22:00:00Z',
    summary: 'Stable anchor. Tracks main; expect drift as main changes.',
  },
  {
    candidate_id: 'bench-wiki-main',
    experiment_group_id: 'group-baselines',
    agent_name: 'wiki-agent',
    agent_version: 'main@9b3c1',
    dataset_id: DATASETS.WIKI_TAG_ACCURACY.id,
    dataset_version: DATASETS.WIKI_TAG_ACCURACY.version,
    evaluator_scores: [
      { evaluator_name: 'tag_recall', mean: 0.42, n_runs: 5 },
      { evaluator_name: 'trajectory_quality', mean: 0.71, n_runs: 5 },
    ],
    run_count: 5,
    producer_metadata: { provider: 'nvidia-build' },
    is_benchmark: true,
    benchmark_slug: 'wiki-main',
    benchmark_name: 'Wiki Agent — Main',
    benchmark_description: 'Continually-updated baseline of the wiki agent on the tag-accuracy dataset.',
    benchmark_promoted_at: '2026-05-29T08:15:00Z',
    benchmark_promoted_via: 'auto',
    benchmark_promoted_by: 'nightly-runner',
    created_at: '2026-05-27T22:00:00Z',
  },
  // --- Deep research group: 2 candidates on QA, 2 on latency ---
  {
    candidate_id: 'cand-dr-minimax-hermes',
    experiment_group_id: 'group-deep-research-optimize',
    agent_name: 'deep-research-agent',
    agent_version: 'feat/minimax-routing@7c9a2',
    dataset_id: DATASETS.DEEP_RESEARCH_QA.id,
    dataset_version: DATASETS.DEEP_RESEARCH_QA.version,
    evaluator_scores: [
      { evaluator_name: 'qa_accuracy', mean: 0.752, n_runs: 5 },
      { evaluator_name: 'trajectory_quality', mean: 0.76, n_runs: 5 },
      { evaluator_name: 'cost_usd', mean: 0.084, n_runs: 5 },
    ],
    run_count: 5,
    producer_metadata: { harness: 'Hermes', model: 'minimax2.7', thinking: 'on' },
    is_benchmark: false,
    created_at: '2026-05-28T17:14:00Z',
    summary: '+7.1% QA accuracy vs main, but ~2x cost. Worth shipping only if latency holds.',
  },
  {
    candidate_id: 'cand-dr-qwen3-openhands',
    experiment_group_id: 'group-deep-research-optimize',
    agent_name: 'deep-research-agent',
    agent_version: 'feat/qwen-routing@a113f',
    dataset_id: DATASETS.DEEP_RESEARCH_QA.id,
    dataset_version: DATASETS.DEEP_RESEARCH_QA.version,
    evaluator_scores: [
      { evaluator_name: 'qa_accuracy', mean: 0.701, n_runs: 5 },
      { evaluator_name: 'trajectory_quality', mean: 0.72, n_runs: 5 },
      { evaluator_name: 'cost_usd', mean: 0.047, n_runs: 5 },
    ],
    run_count: 5,
    producer_metadata: { harness: 'OpenHands', model: 'qwen3.6-35b', thinking: 'on' },
    is_benchmark: false,
    created_at: '2026-05-28T15:02:00Z',
  },
  {
    candidate_id: 'cand-dr-latency-cache',
    experiment_group_id: 'group-deep-research-optimize',
    agent_name: 'deep-research-agent',
    agent_version: 'feat/prefix-cache@e228d',
    dataset_id: DATASETS.DEEP_RESEARCH_LATENCY.id,
    dataset_version: DATASETS.DEEP_RESEARCH_LATENCY.version,
    evaluator_scores: [
      { evaluator_name: 'p95_latency_ms', mean: 1240, n_runs: 5 },
      { evaluator_name: 'cost_usd', mean: 0.038, n_runs: 5 },
    ],
    run_count: 5,
    producer_metadata: { harness: 'OpenHands', model: 'minimax2.7', prefix_cache: 'on' },
    is_benchmark: false,
    created_at: '2026-05-28T11:46:00Z',
  },
  {
    candidate_id: 'cand-dr-latency-skip',
    experiment_group_id: 'group-deep-research-optimize',
    agent_name: 'deep-research-agent',
    agent_version: 'feat/skip-rag@f7820',
    dataset_id: DATASETS.DEEP_RESEARCH_LATENCY.id,
    dataset_version: DATASETS.DEEP_RESEARCH_LATENCY.version,
    evaluator_scores: [
      { evaluator_name: 'p95_latency_ms', mean: 980, n_runs: 5 },
      { evaluator_name: 'cost_usd', mean: 0.031, n_runs: 5 },
    ],
    run_count: 5,
    producer_metadata: { harness: 'OpenHands', model: 'minimax2.7', prefix_cache: 'on', skip_rag_when_short: 'on' },
    is_benchmark: false,
    created_at: '2026-05-28T18:33:00Z',
    summary: 'Skipping RAG on short queries shaves ~260ms off p95.',
  },
  // --- Wiki group: 3 candidates on tag-accuracy ---
  {
    candidate_id: 'cand-wiki-stricter-prompt',
    experiment_group_id: 'group-wiki-prompt-tuning',
    agent_name: 'wiki-agent',
    agent_version: 'feat/stricter-prompt@1d44a',
    dataset_id: DATASETS.WIKI_TAG_ACCURACY.id,
    dataset_version: DATASETS.WIKI_TAG_ACCURACY.version,
    evaluator_scores: [
      { evaluator_name: 'tag_recall', mean: 0.58, n_runs: 5 },
      { evaluator_name: 'trajectory_quality', mean: 0.69, n_runs: 5 },
    ],
    run_count: 5,
    is_benchmark: false,
    created_at: '2026-05-26T13:11:00Z',
  },
  {
    candidate_id: 'cand-wiki-few-shot',
    experiment_group_id: 'group-wiki-prompt-tuning',
    agent_name: 'wiki-agent',
    agent_version: 'feat/few-shot-tags@b9012',
    dataset_id: DATASETS.WIKI_TAG_ACCURACY.id,
    dataset_version: DATASETS.WIKI_TAG_ACCURACY.version,
    evaluator_scores: [
      { evaluator_name: 'tag_recall', mean: 0.64, n_runs: 5 },
      { evaluator_name: 'trajectory_quality', mean: 0.7, n_runs: 5 },
    ],
    run_count: 5,
    is_benchmark: false,
    created_at: '2026-05-27T08:42:00Z',
    summary: 'Few-shot examples in the prompt pushed recall over the 0.6 goal.',
  },
  {
    candidate_id: 'cand-wiki-tool-rewrite',
    experiment_group_id: 'group-wiki-prompt-tuning',
    agent_name: 'wiki-agent',
    agent_version: 'feat/tool-rewrite@66e1c',
    dataset_id: DATASETS.WIKI_TAG_ACCURACY.id,
    dataset_version: DATASETS.WIKI_TAG_ACCURACY.version,
    evaluator_scores: [
      { evaluator_name: 'tag_recall', mean: 0.51, n_runs: 5 },
      { evaluator_name: 'trajectory_quality', mean: 0.74, n_runs: 5 },
    ],
    run_count: 5,
    is_benchmark: false,
    created_at: '2026-05-25T17:18:00Z',
  },
];

// ---------------------------------------------------------------------------
// Lookup helpers
//
// All helpers take a `candidates` list as a parameter so they read off live
// store state rather than the static fixtures. This lets the UI react when a
// Candidate is promoted to / demoted from Benchmark in-session.
// ---------------------------------------------------------------------------

export const getExperimentGroup = (id: string): ExperimentGroup | undefined =>
  EXPERIMENT_GROUPS.find((group) => group.experiment_group_id === id);

export const getCandidatesForGroup = (candidates: Candidate[], groupId: string): Candidate[] =>
  candidates.filter((c) => c.experiment_group_id === groupId);

/**
 * Strict Benchmark compatibility per the technical design: same `dataset_id` AND
 * same `agent_name`. Returns 0..N benchmark candidates that anchor the given
 * Candidate's leaderboard view.
 */
export const getCompatibleBenchmarks = (
  candidates: Candidate[],
  agentName: string,
  datasetId: string,
): Candidate[] =>
  candidates.filter(
    (c) => c.is_benchmark && c.agent_name === agentName && c.dataset_id === datasetId,
  );

/**
 * Unique (dataset_id, dataset_version, dataset display name) tuples present in a
 * group's candidates. Used by the dataset tab switcher on the Group detail view.
 */
export type DatasetSlice = {
  dataset_id: string;
  dataset_version?: string;
  name: string;
};

export const getDatasetSlicesForGroup = (
  candidates: Candidate[],
  groupId: string,
): DatasetSlice[] => {
  const seen = new Map<string, DatasetSlice>();
  for (const candidate of getCandidatesForGroup(candidates, groupId)) {
    const key = `${candidate.dataset_id}::${candidate.dataset_version ?? ''}`;
    if (!seen.has(key)) {
      const meta = Object.values(DATASETS).find((d) => d.id === candidate.dataset_id);
      seen.set(key, {
        dataset_id: candidate.dataset_id,
        dataset_version: candidate.dataset_version,
        name: meta?.name ?? candidate.dataset_id,
      });
    }
  }
  return Array.from(seen.values());
};

/**
 * Highest-score Candidate for the headline evaluator on a given dataset within a
 * group. Picks the leader by the first evaluator's mean (a simple POC heuristic;
 * configurable rank-by lands later).
 */
export const getGroupLeader = (candidates: Candidate[], groupId: string): Candidate | undefined => {
  const groupCandidates = getCandidatesForGroup(candidates, groupId);
  if (groupCandidates.length === 0) {
    return undefined;
  }
  return [...groupCandidates].sort((a, b) => {
    const aScore = a.evaluator_scores[0]?.mean ?? 0;
    const bScore = b.evaluator_scores[0]?.mean ?? 0;
    return bScore - aScore;
  })[0];
};

/**
 * Distinct datasets across every candidate in the workspace. Drives the dataset
 * tab switcher on the cross-group Runs view.
 */
export const getAllDatasetSlices = (candidates: Candidate[]): DatasetSlice[] => {
  const seen = new Map<string, DatasetSlice>();
  for (const candidate of candidates) {
    const key = `${candidate.dataset_id}::${candidate.dataset_version ?? ''}`;
    if (!seen.has(key)) {
      const meta = Object.values(DATASETS).find((d) => d.id === candidate.dataset_id);
      seen.set(key, {
        dataset_id: candidate.dataset_id,
        dataset_version: candidate.dataset_version,
        name: meta?.name ?? candidate.dataset_id,
      });
    }
  }
  return Array.from(seen.values());
};

/**
 * Every Candidate that ran against the given dataset, ranked by the first
 * evaluator's mean (POC heuristic — configurable rank-by lands in M4).
 */
export const getCandidatesForDataset = (
  candidates: Candidate[],
  datasetId: string,
): Candidate[] => {
  return [...candidates.filter((c) => c.dataset_id === datasetId)].sort((a, b) => {
    const aScore = a.evaluator_scores[0]?.mean ?? 0;
    const bScore = b.evaluator_scores[0]?.mean ?? 0;
    return bScore - aScore;
  });
};

/**
 * Workspace-wide tally for the dataset (running totals across all candidates &
 * runs). Powers the "Top Run" hero card stats.
 */
export const getDatasetTotals = (candidates: Candidate[], datasetId: string) => {
  const datasetCandidates = candidates.filter((c) => c.dataset_id === datasetId);
  const totalRuns = datasetCandidates.reduce((sum, c) => sum + c.run_count, 0);
  return {
    candidate_count: datasetCandidates.length,
    total_runs: totalRuns,
  };
};
