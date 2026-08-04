// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  EvalAggregateScoresTable,
  type EvalAggregateScoreRow,
} from '@studio/components/evaluation/EvalAggregateScoresTable';
import { type FC } from 'react';

export type DatasetEvalAggregateScore = EvalAggregateScoreRow;

interface DatasetEvalScoresPanelProps {
  scores: DatasetEvalAggregateScore[];
}

export const DatasetEvalScoresPanel: FC<DatasetEvalScoresPanelProps> = ({ scores }) => (
  <EvalAggregateScoresTable scores={scores} />
);
