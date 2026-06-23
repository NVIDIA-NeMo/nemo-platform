// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ExperimentCostLatencyChart } from '@nemo/studio-plugins-example/experiment-insights/ExperimentCostLatencyChart';
import { contribute, type StudioPlugin } from '@studio/plugins/types';

/**
 * Example plugin demonstrating the slot system: a cost-vs-latency scatter plot of the experiments
 * in view, rendered into the experiment group detail page. Template for real plugins.
 */
export const experimentInsightsPlugin: StudioPlugin = {
  id: 'experiment-insights',
  name: 'Experiment Insights',
  description: 'Demo: cost-vs-latency plot for the experiments in view.',
  workspaces: ['default'],
  contributions: [
    contribute({
      slot: 'experiments.group.afterSearch',
      id: 'experiment-insights:cost-latency',
      render: ExperimentCostLatencyChart,
    }),
  ],
};
