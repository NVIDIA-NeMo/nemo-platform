// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { SegmentedControl, Stack } from '@nvidia/foundations-react-core';
import type { EvalJobRow } from '@studio/api/evaluation/utils';
import { EvaluationsTable } from '@studio/routes/agents/AgentDetailRoute/evaluations/EvaluationsTable';
import { ExperimentsTable } from '@studio/routes/agents/AgentDetailRoute/evaluations/ExperimentsTable';
import { groupByExperiment } from '@studio/routes/agents/AgentDetailRoute/evaluations/groupByExperiment';
import { JobsTable } from '@studio/routes/agents/AgentDetailRoute/evaluations/JobsTable';
import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';
import { type FC, useMemo, useState } from 'react';

const VIEW_EVALUATIONS = 'evaluations';
const VIEW_EXPERIMENTS = 'experiments';
const VIEW_JOBS = 'jobs';

// Jobs first, and the default: a run is visible here the instant it is submitted, whereas the
// other two views stay empty until it publishes.
const VIEW_ITEMS = [
  { value: VIEW_JOBS, children: 'Active Jobs' },
  { value: VIEW_EVALUATIONS, children: 'Completed Evaluations' },
  { value: VIEW_EXPERIMENTS, children: 'Experiments' },
];

interface EvaluationsTabProps {
  workspace: string;
  evals: AgentEvaluationRow[];
  jobs: EvalJobRow[];
}

/** Three readings of the same work: published evaluations flat, rolled up by experiment, or the
 *  jobs that produced them. Jobs are separate because they answer a different question — what is
 *  running right now — which Intake cannot answer until a run publishes. */
export const EvaluationsTab: FC<EvaluationsTabProps> = ({ workspace, evals, jobs }) => {
  const [view, setView] = useState<string>(VIEW_JOBS);
  const experiments = useMemo(() => groupByExperiment(evals), [evals]);

  // No panel wrapper: the tab is already labelled "Evaluations", so a titled card repeats it.
  return (
    <Stack gap="density-lg">
      <SegmentedControl
        className="w-fit"
        aria-label="Evaluation view"
        value={view}
        onValueChange={setView}
        items={VIEW_ITEMS}
      />
      {view === VIEW_EXPERIMENTS && (
        <ExperimentsTable workspace={workspace} experiments={experiments} />
      )}
      {view === VIEW_JOBS && <JobsTable workspace={workspace} jobs={jobs} evaluations={evals} />}
      {view === VIEW_EVALUATIONS && <EvaluationsTable workspace={workspace} evaluations={evals} />}
    </Stack>
  );
};
