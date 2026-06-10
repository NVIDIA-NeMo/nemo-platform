// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ExcludedChatCompletionMessageParam } from '@nemo/common/src/types/chat';
import { evaluatorDownloadEvaluateJobResult } from '@nemo/sdk/generated/evaluator/api';
import { useQuery } from '@tanstack/react-query';

export interface EvaluationMetrics {
  bleu?: {
    scores?: {
      sentence?: {
        value: number;
      };
    };
  };
  [key: string]: unknown;
}

export type EvaluationItem =
  | {
      prompt: string;
      ideal_response: string;
    }
  | {
      messages: ExcludedChatCompletionMessageParam[];
    };

export interface EvaluationSample {
  output_text: string;
}
export interface EvaluationResultItem {
  item: EvaluationItem;
  sample: EvaluationSample;
  metrics: EvaluationMetrics;
}

interface RowScore {
  index: number;
  row: Record<string, unknown>;
  scores?: Record<string, number>;
  error?: string;
}

function mapRowScores(rows: RowScore[]): EvaluationResultItem[] {
  return rows.map((row) => ({
    item: {
      prompt: String(row.row?.prompt ?? row.row?.input ?? ''),
      ideal_response: String(row.row?.ideal_response ?? row.row?.reference ?? ''),
      ...(row.row?.messages
        ? { messages: row.row.messages as ExcludedChatCompletionMessageParam[] }
        : {}),
    } as EvaluationItem,
    sample: {
      output_text: String(row.row?.output ?? row.row?.output_text ?? ''),
    },
    metrics: mapScores(row.scores),
  }));
}

function mapScores(scores?: Record<string, number>): EvaluationMetrics {
  if (!scores) return {};

  const result: EvaluationMetrics = {};

  for (const [key, value] of Object.entries(scores)) {
    if (key === 'sentence' || key === 'corpus') {
      if (!result.bleu) {
        result.bleu = { scores: {} };
      }
      if (!result.bleu!.scores) {
        result.bleu!.scores = {};
      }
      (result.bleu!.scores as Record<string, { value: number }>)[key] = { value };
    } else {
      result[key] = value;
    }
  }

  return result;
}

async function fetchEvaluationResults(
  workspace: string,
  jobName: string,
  name: string
): Promise<EvaluationResultItem[]> {
  const blob = await evaluatorDownloadEvaluateJobResult(workspace, jobName, name);

  const text = await blob.text();
  const parsed = JSON.parse(text);

  const rows: RowScore[] = Array.isArray(parsed)
    ? parsed
    : (parsed.data ?? parsed.row_scores ?? []);

  return mapRowScores(rows);
}

export const useEvaluationDownloadResultsById = (
  workspace: string,
  jobName: string,
  name = 'row_scores'
) => {
  return useQuery<EvaluationResultItem[], Error>({
    queryKey: ['evaluationDownloadResults', workspace, jobName, name],
    queryFn: () => fetchEvaluationResults(workspace, jobName, name),
    enabled: !!workspace && !!jobName,
  });
};
