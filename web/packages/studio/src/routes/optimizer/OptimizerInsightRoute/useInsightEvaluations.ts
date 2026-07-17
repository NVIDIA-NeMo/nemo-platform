// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useListEvaluations, useListExperimentGroups } from '@nemo/sdk/generated/platform/api';
import type {
  EvaluationResponse,
  ExperimentGroupResponse,
} from '@nemo/sdk/generated/platform/schema';

export interface InsightEvaluations {
  /** The experiment group seeded by this insight, if one exists. */
  group: ExperimentGroupResponse | undefined;
  /** Evaluations belonging to that group (empty until a group is found). */
  evaluations: EvaluationResponse[];
  isLoading: boolean;
}

/**
 * Evaluations to show on an insight page.
 *
 * The insight → evaluation link is indirect: an {@link ExperimentGroupResponse}
 * carries `insight_id`, and evaluations belong to a group via
 * `experiment_group_id` (evaluations themselves have no `insight_id`). We filter
 * the groups list server-side by `insight_id` so the match doesn't depend on how
 * many groups the workspace has. The product model is one group seeded per
 * insight, so we take the first match and load that group's evaluations.
 */
export const useInsightEvaluations = (workspace: string, insightId: string): InsightEvaluations => {
  const { data: groupsPage, isLoading: groupsLoading } = useListExperimentGroups(
    workspace,
    { filter: { insight_id: insightId }, page_size: 1 },
    { query: { enabled: !!insightId } }
  );

  const group = groupsPage?.data?.[0];

  const { data: evaluationsPage, isLoading: evaluationsLoading } = useListEvaluations(
    workspace,
    { filter: { experiment_group_id: group?.id }, page_size: 100, sort: '-created_at' },
    { query: { enabled: !!group?.id } }
  );

  return {
    group,
    evaluations: group ? (evaluationsPage?.data ?? []) : [],
    isLoading: groupsLoading || (!!group?.id && evaluationsLoading),
  };
};
