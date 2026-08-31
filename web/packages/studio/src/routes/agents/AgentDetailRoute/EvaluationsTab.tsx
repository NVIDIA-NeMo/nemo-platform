// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PlatformJobTerminalStatuses } from '@nemo/common/src/constants/query';
import { SegmentedControl, Stack, Text } from '@nvidia/foundations-react-core';
import type { EvalJobRow } from '@studio/api/evaluation/utils';
import { EvaluationsTable } from '@studio/routes/agents/AgentDetailRoute/evaluations/EvaluationsTable';
import { ExperimentsTable } from '@studio/routes/agents/AgentDetailRoute/evaluations/ExperimentsTable';
import { groupByExperiment } from '@studio/routes/agents/AgentDetailRoute/evaluations/groupByExperiment';
import { JobsTable } from '@studio/routes/agents/AgentDetailRoute/evaluations/JobsTable';
import type { AgentEvaluationRow } from '@studio/routes/agents/AgentDetailRoute/useAgentDetails';
import { type FC, useMemo, useState } from 'react';

const VIEW_EVALUATIONS = 'evaluations';
const VIEW_EXPERIMENTS = 'experiments';

const VIEW_ITEMS = [
  { value: VIEW_EVALUATIONS, children: 'Completed Evaluations' },
  { value: VIEW_EXPERIMENTS, children: 'Experiments' },
];

interface EvaluationsTabProps {
  workspace: string;
  /** The agent whose evaluations these are, seeded into a re-run started from a row. */
  agentName?: string;
  evals: AgentEvaluationRow[];
  jobs: EvalJobRow[];
}

/** Two readings of the same published work — flat evaluations or rolled up by experiment — with
 *  the jobs still running pinned above them. Active jobs answer a different question ("what is
 *  running right now") that Intake cannot answer until a run publishes, so they get their own
 *  always-visible section instead of a segmented-control tab. */
export const EvaluationsTab: FC<EvaluationsTabProps> = ({
  workspace,
  agentName,
  evals,
  jobs,
}) => {
  const [view, setView] = useState<string>(VIEW_EVALUATIONS);
  const experiments = useMemo(() => groupByExperiment(evals), [evals]);
  const activeJobs = useMemo(
    () =>
      jobs.filter((job) => !PlatformJobTerminalStatuses.some((status) => status === job.status)),
    [jobs]
  );

  return (
    <Stack gap="density-lg" className="w-full">
      {activeJobs.length > 0 && (
        <Stack gap="density-sm">
          <Text kind="title/sm">Active jobs</Text>
          <JobsTable workspace={workspace} jobs={activeJobs} evaluations={evals} />
        </Stack>
      )}
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
      {view === VIEW_EVALUATIONS && (
        <EvaluationsTable
          workspace={workspace}
          agentName={agentName}
          evaluations={evals}
          jobs={jobs}
        />
      )}
    </Stack>
  );
};
