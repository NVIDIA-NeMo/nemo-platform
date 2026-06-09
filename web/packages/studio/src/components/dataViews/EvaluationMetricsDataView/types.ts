// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/** A metric list item augmented with a stable `id` field for table row keying. */
export interface MetricItemWithId {
  id: string;
  name?: string;
  description?: string;
  type?: string;
  created_at?: string;
  updated_at?: string;
  workspace?: string;
  [key: string]: unknown;
}

export interface EvaluationMetricsDataViewProps {
  workspace: string;
  onRowClick?: (metric: MetricItemWithId) => void;
}
