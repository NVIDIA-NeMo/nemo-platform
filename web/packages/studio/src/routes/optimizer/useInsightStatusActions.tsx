// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  getOptimizerGetInsightQueryKey,
  getOptimizerListInsightsQueryKey,
  useOptimizerUpdateInsight,
  type Insight,
  type InsightStatus,
} from '@studio/api/optimizer';
import { InsightOpenModal } from '@studio/routes/optimizer/InsightOpenModal';
import { useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useState } from 'react';

export interface InsightStatusActions {
  /** Runs an action returned by `insightActions`. */
  run: (insight: Insight, target: InsightStatus) => void;
  /** True while a status change is in flight. */
  isPending: boolean;
  /** The run-experiment modal. Render it once per page. */
  slotModal: ReactNode;
}

/**
 * Status-change behaviour shared by the insight list rows and the insight page header,
 * so both offer the same actions and refresh the same queries.
 */
export const useInsightStatusActions = (workspace: string): InsightStatusActions => {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [runExperimentFor, setRunExperimentFor] = useState<Insight | null>(null);

  const { mutate, isPending } = useOptimizerUpdateInsight({
    mutation: {
      onSuccess: (_insight, { insightId }) => {
        queryClient.invalidateQueries({
          queryKey: getOptimizerGetInsightQueryKey(workspace, insightId),
        });
        queryClient.invalidateQueries({
          queryKey: getOptimizerListInsightsQueryKey(workspace),
        });
      },
      onError: () => toast.error('Failed to update insight.'),
    },
  });

  return {
    // The external agent changes the status after it creates the experiment.
    run: (insight, target) => {
      if (target === 'open') {
        setRunExperimentFor(insight);
        return;
      }
      mutate({ workspace, insightId: insight.id, data: { status: target } });
    },
    isPending,
    slotModal: runExperimentFor ? (
      <InsightOpenModal
        open
        insight={runExperimentFor}
        workspace={workspace}
        onClose={() => setRunExperimentFor(null)}
      />
    ) : null,
  };
};
