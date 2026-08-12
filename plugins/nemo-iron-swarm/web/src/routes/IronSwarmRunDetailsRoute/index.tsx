// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { usePlatformSdk } from '@iron-swarm/api/platform';
import { HardenPanel } from '@iron-swarm/components/HardenPanel';
import {
  pendingInterview,
  pendingReview,
  type InterviewAnswer,
  type SuiteRow,
} from '@iron-swarm/components/hitlTypes';
import { InterviewPanel } from '@iron-swarm/components/InterviewPanel';
import { ReviewPanel } from '@iron-swarm/components/ReviewPanel';
import { MessageFeed } from '@iron-swarm/components/swarm/MessageFeed';
import { NodeDetail } from '@iron-swarm/components/swarm/NodeDetail';
import { SwarmGraph } from '@iron-swarm/components/swarm/SwarmGraph';
import { deriveSwarmState, NODES } from '@iron-swarm/components/swarm/swarmModel';
import { useSwarmEvents } from '@iron-swarm/components/swarm/useSwarmEvents';
import { useMitigations } from '@iron-swarm/components/useMitigations';
import { useIronSwarmGetRun } from '@iron-swarm/generated/api';
import { useBreadcrumbs, useWorkspace } from '@iron-swarm/host';
import { getIronSwarmRunListRoute } from '@iron-swarm/paths';
import { AccessibleTitle, CancelJobButton, JOB_POLLING_INTERVAL_MS, getJobRefetchInterval } from '@nemo/common';
import {
  Badge,
  Banner,
  Card,
  Flex,
  Grid,
  PageHeader,
  Stack,
  TabsContent,
  TabsList,
  TabsRoot,
  TabsTrigger,
  Text,
} from '@nvidia/foundations-react-core';
import { FC, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router';

const Pill: FC<{ label: string; tone?: 'good' | 'active' }> = ({ label, tone }) => (
  <span
    className={`rounded-full border px-3 py-1 text-xs uppercase tracking-wide ${
      tone === 'good'
        ? 'border-green-500/40 text-green-400'
        : tone === 'active'
          ? 'border-cyan-500/40 text-cyan-400'
          : 'border-gray-600 text-gray-400'
    }`}
  >
    {label}
  </span>
);

export const IronSwarmRunDetailsRoute: FC = () => {
  const workspace = useWorkspace();
  const { ironSwarmRunName = '' } = useParams<{ ironSwarmRunName: string }>();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const { data: run } = useIronSwarmGetRun(workspace, ironSwarmRunName, {
    query: {
      enabled: Boolean(ironSwarmRunName),
      refetchInterval: (query) =>
        query.state.data?.status === 'running' ? JOB_POLLING_INTERVAL_MS : false,
    },
  });

  // Live swarm state, folded from the run's event stream. Stop polling once the run is terminal —
  // otherwise a finished run is polled for as long as the tab stays open.
  const events = useSwarmEvents(
    workspace,
    ironSwarmRunName,
    Boolean(run?.status) && run?.status !== 'running'
  );
  const swarm = useMemo(() => deriveSwarmState(events), [events]);

  // The platform job behind this run drives the interview/review HITL over its status_details.
  const jobName = run?.job_id ?? '';
  const { useJobsGetJob, useJobsUpdateJobStatusDetails } = usePlatformSdk();
  const { data: job } = useJobsGetJob(workspace, jobName, {
    query: {
      enabled: Boolean(jobName),
      refetchInterval: (query) => getJobRefetchInterval(query.state.data?.status),
    },
  });
  const patch = useJobsUpdateJobStatusDetails();
  const details = job?.status_details as Record<string, unknown> | undefined;
  const interview = pendingInterview(details);
  const review = pendingReview(details);

  // Hardening output (before/after policy + workflow + selectable defenses), fetched from the job results
  // API once the run ends.
  const {
    mitigations,
    recommendations,
    defenses,
    isLoading: mitigationsLoading,
    hasMitigations,
  } = useMitigations(workspace, jobName);

  useBreadcrumbs({
    items: [
      { href: getIronSwarmRunListRoute(workspace), slotLabel: 'Iron Swarm' },
      { slotLabel: ironSwarmRunName },
    ],
  });

  const respond = (data: Record<string, unknown>) =>
    patch.mutate({ workspace, name: jobName, data });
  const onInterview = (answers: InterviewAnswer[]) =>
    interview && respond({ interview_response: { round: interview.round, answers } });
  const onReview = (suite: SuiteRow[]) =>
    review && respond({ review_response: { round: review.round, suite } });

  const selectedNode = NODES.find((n) => n.id === selectedId) ?? null;

  // Benign generation (and its interview) is a manifest activity, so a normal war-game run is pure mission
  // control. The Interview tab is a fallback — it appears only if a run genuinely pauses for input.
  const hitlPending = Boolean(interview || review);
  const [tab, setTab] = useState('swarm');
  // Owned here (not in HardenPanel) so an in-flight sanity check survives tab switches — the Harden
  // tab's content unmounts when another tab is active.
  const [sanityJob, setSanityJob] = useState<string>();
  const [composedWorkflow, setComposedWorkflow] = useState<string>();
  useEffect(() => {
    if (hitlPending) setTab('interview');
  }, [hitlPending]);

  const swarmView = (
    <Grid cols={{ base: 1, xl: 2 }} gap="density-xl">
      <Card className="h-[560px] p-2">
        <SwarmGraph swarm={swarm} selectedId={selectedId} onSelect={setSelectedId} />
      </Card>
      <Stack gap="density-xl" className="h-[560px] min-h-0">
        {/* Agent view sits a little smaller than the live feed (5:6). */}
        <Card className="min-h-0 flex-[5] overflow-auto p-4">
          <NodeDetail node={selectedNode} swarm={swarm} />
        </Card>
        {/* KUI Card wraps children in a grid `.nv-card-content` that grows to fit; force it to a bounded
            flex column so the feed scrolls internally instead of stretching the page. */}
        <Card className="min-h-0 flex-[6] p-4 [&_.nv-card-content]:flex [&_.nv-card-content]:min-h-0 [&_.nv-card-content]:flex-col">
          <Text kind="body/semibold/md" className="mb-2 shrink-0">
            Live Agent Feed
          </Text>
          <div className="min-h-0 flex-1">
            <MessageFeed events={events} />
          </div>
        </Card>
      </Stack>
    </Grid>
  );

  // A failed run surfaces its classified cause (from the run record, falling back to the platform job's
  // error_details or the summary) as an inline error banner.
  const jobErrorMessage = (job?.error_details as { message?: unknown } | undefined)?.message;
  const failureMessage =
    run?.error_message ||
    (typeof jobErrorMessage === 'string' ? jobErrorMessage : '') ||
    run?.summary ||
    'War-game run failed.';

  return (
    <AccessibleTitle title={`Iron Swarm — ${ironSwarmRunName}`}>
      <Stack className="min-h-full" gap="density-xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading={run?.agent ? `Hardening ${run.agent}` : 'War-Game Run'}
          slotDescription={run?.summary}
          slotActions={
            <Flex gap="density-sm" align="center">
              {swarm.round > 0 && <Pill label={`Round ${swarm.round}`} />}
              {swarm.phase && (
                <Pill label={swarm.phase} tone={swarm.finalPass ? 'good' : 'active'} />
              )}
              {run?.job_id && (
                <CancelJobButton
                  workspace={workspace}
                  jobName={run.job_id}
                  jobStatus={job?.status}
                  compact
                />
              )}
            </Flex>
          }
        />

        {run?.status === 'failed' && (
          <Banner kind="inline" status="error">
            <Stack gap="density-xs">
              <Text kind="body/semibold/md">{failureMessage}</Text>
              {run.error_remediation ? (
                <Text kind="body/regular/sm">{run.error_remediation}</Text>
              ) : null}
            </Stack>
          </Banner>
        )}

        {hitlPending || hasMitigations ? (
          <TabsRoot value={tab} onValueChange={setTab}>
            <TabsList>
              <TabsTrigger value="swarm">Swarm</TabsTrigger>
              {hitlPending ? (
                <TabsTrigger value="interview">
                  <Flex gap="density-xs" align="center">
                    Interview
                    <Badge color="yellow">Action required</Badge>
                  </Flex>
                </TabsTrigger>
              ) : null}
              {hasMitigations ? (
                <TabsTrigger value="mitigations">
                  <Flex gap="density-xs" align="center">
                    Harden
                    {(defenses.length || recommendations.length) > 0 && (
                      <Badge color="green">{defenses.length || recommendations.length}</Badge>
                    )}
                  </Flex>
                </TabsTrigger>
              ) : null}
            </TabsList>

            <TabsContent value="swarm" className="p-0 pt-4">
              {swarmView}
            </TabsContent>

            {hitlPending ? (
              <TabsContent value="interview" className="p-0 pt-4">
                <Card className="min-h-[420px] p-6">
                  {interview ? (
                    <InterviewPanel
                      prompt={interview}
                      loading={patch.isPending}
                      onSubmit={onInterview}
                    />
                  ) : review ? (
                    <ReviewPanel
                      suite={review.suite}
                      loading={patch.isPending}
                      onSubmit={onReview}
                    />
                  ) : null}
                </Card>
              </TabsContent>
            ) : null}

            {hasMitigations ? (
              <TabsContent value="mitigations" className="p-0 pt-4">
                <HardenPanel
                  mitigations={mitigations}
                  defenses={defenses}
                  isLoading={mitigationsLoading}
                  workspace={workspace}
                  runName={ironSwarmRunName}
                  agentName={run?.agent}
                  manifestId={run?.manifest_id}
                  hitlogFileset={run?.hitlog_fileset}
                  sanityJob={sanityJob}
                  onSanityJobChange={setSanityJob}
                  composedWorkflow={composedWorkflow}
                  onComposedWorkflowChange={setComposedWorkflow}
                />
              </TabsContent>
            ) : null}
          </TabsRoot>
        ) : (
          swarmView
        )}
      </Stack>
    </AccessibleTitle>
  );
};
