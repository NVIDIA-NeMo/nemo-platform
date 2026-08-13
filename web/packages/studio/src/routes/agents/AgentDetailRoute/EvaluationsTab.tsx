// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SegmentedControl, Stack } from '@nvidia/foundations-react-core';
import { EvaluationsTable } from '@studio/routes/agents/AgentDetailRoute/evaluations/EvaluationsTable';
import { ExperimentsTable } from '@studio/routes/agents/AgentDetailRoute/evaluations/ExperimentsTable';
import { groupByExperiment } from '@studio/routes/agents/AgentDetailRoute/evaluations/groupByExperiment';
import { DetailPanel } from '@studio/routes/agents/AgentDetailRoute/overview/DetailPanel';
import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';
import { type FC, useMemo, useState } from 'react';

const VIEW_EVALUATIONS = 'evaluations';
const VIEW_EXPERIMENTS = 'experiments';

const VIEW_ITEMS = [
  { value: VIEW_EVALUATIONS, children: 'Evaluations' },
  { value: VIEW_EXPERIMENTS, children: 'Experiments' },
];

interface EvaluationsTabProps {
  workspace: string;
  evals: AgentEvaluationRow[];
}

/** The agent's published evaluations, either flat or rolled up by experiment. Both views read the
 *  same evaluations; only the grouping differs, which is why this is a toggle and not a tab. */
export const EvaluationsTab: FC<EvaluationsTabProps> = ({ workspace, evals }) => {
  const [view, setView] = useState<string>(VIEW_EVALUATIONS);
  const experiments = useMemo(() => groupByExperiment(evals), [evals]);

  return (
    <DetailPanel title="Evaluations" flush>
      <Stack gap="density-lg" className="p-4">
        <SegmentedControl
          className="w-fit"
          aria-label="Group evaluations"
          value={view}
          onValueChange={setView}
          items={VIEW_ITEMS}
        />
        {view === VIEW_EXPERIMENTS ? (
          <ExperimentsTable workspace={workspace} experiments={experiments} />
        ) : (
          <EvaluationsTable workspace={workspace} evaluations={evals} />
        )}
      </Stack>
    </DetailPanel>
  );
};
