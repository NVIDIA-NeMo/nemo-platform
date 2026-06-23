// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getExperimentDetailRoute } from '@studio/routes/utils';

/**
 * Workspace-relative path for the error report page, registered via the plugin's `routes`. Sits
 * directly under the single-experiment detail route, so it shares its `:param` segments.
 */
export const EXPERIMENT_ERRORS_ROUTE_PATH =
  'experiment/:experimentGroupName/:experimentName/errors';

/** Absolute link to the error report page — the detail route plus the `errors` segment. */
export const getExperimentErrorReportRoute = (
  workspace: string,
  experimentGroupName: string,
  experimentName: string
): string => `${getExperimentDetailRoute(workspace, experimentGroupName, experimentName)}/errors`;
