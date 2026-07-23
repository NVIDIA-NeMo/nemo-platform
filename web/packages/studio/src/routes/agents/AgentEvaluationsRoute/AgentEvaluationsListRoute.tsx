// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { AgentEvaluationsDataView } from '@studio/components/dataViews/AgentEvaluationsDataView';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { SubmitEvaluationModal } from '@studio/routes/agents/AgentEvaluationsRoute/components/SubmitEvaluationModal';
import { getAgentsListRoute } from '@studio/routes/utils';
import { useState, type FC } from 'react';

export const AgentEvaluationsListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const [submitOpen, setSubmitOpen] = useState(false);
  useBreadcrumbs({
    items: [
      { slotLabel: 'Agents', href: getAgentsListRoute(workspace) },
      { slotLabel: 'Evaluations' },
    ],
  });

  return (
    <AccessibleTitle title={`Agent Evaluations for ${workspace}`}>
      <Stack className="h-full overflow-hidden" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Agent Evaluations"
          slotDescription="Evaluation jobs run against deployed agents — submitted by the optimizer apply flow or directly via the evaluate-agent job API."
          slotActions={
            <Button kind="primary" color="brand" onClick={() => setSubmitOpen(true)}>
              Run Evaluation
            </Button>
          }
        />
        <AgentEvaluationsDataView />
      </Stack>
      <SubmitEvaluationModal
        open={submitOpen}
        onClose={() => setSubmitOpen(false)}
        workspace={workspace}
      />
    </AccessibleTitle>
  );
};
