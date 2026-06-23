// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { ExperimentResponse } from '@nemo/sdk/generated/platform/schema';

/** A single plottable experiment: mean cost (USD) against mean latency (ms). */
export interface CostLatencyPoint {
  name: string;
  cost: number;
  latency: number;
}

/** The subset of an experiment row the cost-vs-latency plot reads. */
type CostLatencySource = Pick<ExperimentResponse, 'name' | 'cost_usd' | 'latency_ms'>;

/**
 * Distills experiment rows into scatter points, keeping only experiments that report both a mean
 * cost and a mean latency — a point needs both coordinates, so rows missing either are dropped.
 * A group whose experiments lack these rollups plots nothing, and the chart hides itself.
 */
export const toCostLatencyPoints = (
  experiments: readonly CostLatencySource[]
): CostLatencyPoint[] =>
  experiments.flatMap((experiment) => {
    const cost = experiment.cost_usd?.mean;
    const latency = experiment.latency_ms?.mean;
    if (cost == null || latency == null) return [];
    return [{ name: experiment.name, cost, latency }];
  });
