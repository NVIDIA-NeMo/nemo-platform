// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useEvaluatorGetEvaluateJobResult } from '@nemo/sdk/generated/evaluator/api';
import type { DatasetEvalRow } from '@studio/components/evaluation/Jobs/datasetEval/DatasetEvalRowResultsPanel';
import type { DatasetEvalAggregateScore } from '@studio/components/evaluation/Jobs/datasetEval/DatasetEvalScoresPanel';
import { useQuery } from '@tanstack/react-query';

interface AggregateScoresArtifact {
  scores: DatasetEvalAggregateScore[] | Record<string, Record<string, number>>;
}

const toAggregateScores = (
  artifact: AggregateScoresArtifact | undefined
): DatasetEvalAggregateScore[] => {
  const raw = artifact?.scores;
  if (!raw) return [];
  if (Array.isArray(raw)) return raw.filter((score) => !!score?.name);
  return Object.entries(raw).map(([name, fields]) => ({ name, ...fields }));
};

const parseRowScores = (text: string): DatasetEvalRow[] =>
  text
    .split('\n')
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line) as DatasetEvalRow);

const downloadJson = async <T>(url: string, label: string): Promise<T> => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to download ${label}: ${response.statusText}`);
  return (await response.json()) as T;
};

export const useDatasetEvalResults = (workspace: string, jobName: string, status?: string) => {
  const isPending = status === 'pending' || status === 'active';
  const hasFailed = status === 'error' || status === 'cancelled';
  const enabled = !!workspace && !!jobName && !isPending && !hasFailed;

  const {
    data: scoresMetadata,
    isLoading: isLoadingScoresMetadata,
    error: scoresMetadataError,
  } = useEvaluatorGetEvaluateJobResult(workspace, jobName, 'aggregate-scores', {
    query: { enabled, retry: 3 },
  });

  const {
    data: scoresArtifact,
    isLoading: isLoadingScores,
    error: scoresError,
  } = useQuery({
    queryKey: ['dataset-eval-aggregate-scores', workspace, jobName, scoresMetadata?.download_url],
    queryFn: () =>
      downloadJson<AggregateScoresArtifact>(scoresMetadata?.download_url ?? '', 'results'),
    enabled: !!scoresMetadata?.download_url,
    retry: 3,
  });

  const {
    data: rowsMetadata,
    isLoading: isLoadingRowsMetadata,
    error: rowsMetadataError,
  } = useEvaluatorGetEvaluateJobResult(workspace, jobName, 'row-scores', {
    query: { enabled, retry: 3 },
  });

  const {
    data: rows,
    isLoading: isLoadingRowsDownload,
    error: rowsError,
  } = useQuery({
    queryKey: ['dataset-eval-row-scores', workspace, jobName, rowsMetadata?.download_url],
    queryFn: () =>
      downloadText(rowsMetadata?.download_url ?? '', 'row scores').then(parseRowScores),
    enabled: !!rowsMetadata?.download_url,
    retry: 3,
  });

  return {
    scores: toAggregateScores(scoresArtifact),
    rows: rows ?? [],
    isPending,
    hasFailed,
    isLoadingScores: isLoadingScoresMetadata || isLoadingScores,
    isLoadingRows: isLoadingRowsMetadata || isLoadingRowsDownload,
    scoresError: scoresMetadataError || scoresError,
    rowsError: rowsMetadataError || rowsError,
  };
};
