// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ExperimentErrorBanner } from '@nemo/studio-plugins-example/experiment-errors/ExperimentErrorBanner';
import { ExperimentErrorReportRoute } from '@nemo/studio-plugins-example/experiment-errors/ExperimentErrorReportRoute';
import { EXPERIMENT_ERRORS_ROUTE_PATH } from '@nemo/studio-plugins-example/experiment-errors/routePath';
import { contribute, type StudioPlugin } from '@studio/plugins/types';

/**
 * Cross-tier experiment plugin demonstrating both extension kinds at once:
 * - a **slot banner** on the experiment detail page summarizing the experiment's error spans, and
 * - a **standalone route** (`/.../errors`) the banner links to, rendering the full error report
 *   (errors-by-type table + the individual error spans).
 *
 * Both tables are backed by query plugins (`experiment-error-summary`, `experiment-error-spans`)
 * that aggregate over the whole experiment, not just a loaded test-case page.
 */
export const experimentErrorsPlugin: StudioPlugin = {
  id: 'experiment-errors',
  name: 'Experiment Errors',
  description:
    'Banner + error report page surfacing an experiment’s error spans, grouped by type and listed individually.',
  workspaces: ['default'],
  contributions: [
    contribute({
      slot: 'experiments.detail.beforeSearch',
      id: 'experiment-errors:banner',
      order: 1,
      render: ExperimentErrorBanner,
    }),
  ],
  routes: [
    {
      id: 'experiment-errors:report',
      path: EXPERIMENT_ERRORS_ROUTE_PATH,
      render: ExperimentErrorReportRoute,
    },
  ],
};
