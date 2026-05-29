// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getExperimentGroupRoute, getExperimentsRoute } from '@studio/routes/utils';
import {
  Badge,
  Button,
  Flex,
  FormField,
  Grid,
  PageHeader,
  Panel,
  Stack,
  Text,
  TextArea,
  TextInput,
} from '@nvidia/foundations-react-core';
import { Award, ChevronLeft, FlaskConical, ShieldAlert, Trophy, Undo2, X } from 'lucide-react';
import { type FC, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { EXPERIMENT_GROUPS } from '../ExperimentsListRoute/fixtures';
import {
  type Candidate,
  demoteCandidate,
  getCurrentBenchmark,
  promoteCandidate,
  useCandidate,
  useCandidates,
} from '../ExperimentsListRoute/store';

export const ExperimentCandidateDetailRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const { candidateId } = useParams<{ candidateId: string }>();
  const candidate = useCandidate(candidateId);
  const candidates = useCandidates();

  const [showPromote, setShowPromote] = useState(false);
  const [showDemote, setShowDemote] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | undefined>();

  const groupName = useMemo(() => {
    if (!candidate?.experiment_group_id) {
      return undefined;
    }
    return EXPERIMENT_GROUPS.find((g) => g.experiment_group_id === candidate.experiment_group_id)
      ?.name;
  }, [candidate]);

  const currentBenchmark = useMemo(
    () =>
      candidate
        ? getCurrentBenchmark(candidates, candidate.agent_name, candidate.dataset_id)
        : undefined,
    [candidates, candidate],
  );

  if (!candidate) {
    return (
      <Stack gap="density-md" className="p-density-2xl">
        <Text kind="title/md">Candidate not found</Text>
        <Link to={getExperimentsRoute(workspace)} className="no-underline">
          <Flex align="center" gap="density-xs" className="text-accent">
            <ChevronLeft />
            <Text kind="body/regular/sm">Back to Experiments</Text>
          </Flex>
        </Link>
      </Stack>
    );
  }

  const wouldReplace =
    currentBenchmark && currentBenchmark.candidate_id !== candidate.candidate_id
      ? currentBenchmark
      : undefined;

  return (
    <AccessibleTitle title={candidate.candidate_id}>
      <Stack gap="density-2xl" className="p-density-2xl">
        <Stack gap="density-md">
          <Link to={getExperimentsRoute(workspace)} className="no-underline">
            <Flex align="center" gap="density-xs" className="text-secondary">
              <ChevronLeft size={16} />
              <Text kind="body/regular/sm">Experiments</Text>
            </Flex>
          </Link>
          <PageHeader
            slotHeading={
              <Flex align="center" gap="density-sm" wrap="wrap">
                {candidate.is_benchmark && <Award className="text-accent" />}
                <FlaskConical />
                <Text kind="title/lg" className="font-mono break-all">
                  {candidate.candidate_id}
                </Text>
                {candidate.is_benchmark && <Badge kind="outline">Benchmark</Badge>}
              </Flex>
            }
            slotDescription={candidate.summary}
          />
        </Stack>

        <Grid className="grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)] gap-density-2xl items-start">
          <Stack gap="density-lg" className="min-w-0">
            <CandidateMetadataCard
              candidate={candidate}
              workspace={workspace}
              groupName={groupName}
            />
            <CandidateScoresCard candidate={candidate} />
          </Stack>
          <Stack gap="density-lg">
            {candidate.is_benchmark ? (
              <Panel elevation="high" slotHeading="Benchmark status">
                <Stack gap="density-md">
                  <Text kind="body/regular/sm">
                    This Candidate is the current Benchmark for{' '}
                    <span className="font-semibold">
                      {candidate.agent_name} × {candidate.dataset_id}
                    </span>
                    .
                  </Text>
                  {showDemote ? (
                    <DemoteConfirmation
                      candidate={candidate}
                      onCancel={() => setShowDemote(false)}
                      onConfirm={() => {
                        demoteCandidate(candidate.candidate_id);
                        setShowDemote(false);
                      }}
                    />
                  ) : (
                    <Button kind="secondary" onClick={() => setShowDemote(true)}>
                      <Undo2 />
                      Demote
                    </Button>
                  )}
                </Stack>
              </Panel>
            ) : (
              <Panel elevation="high" slotHeading="Promote to Benchmark">
                <Stack gap="density-md">
                  {wouldReplace ? (
                    <Text kind="body/regular/sm" className="text-secondary">
                      Promoting will replace the current Benchmark{' '}
                      <span className="font-semibold">
                        {wouldReplace.benchmark_name ?? wouldReplace.candidate_id}
                      </span>{' '}
                      for {candidate.agent_name} × {candidate.dataset_id}.
                    </Text>
                  ) : (
                    <Text kind="body/regular/sm" className="text-secondary">
                      No Benchmark exists yet for {candidate.agent_name} × {candidate.dataset_id}.
                      Promoting this Candidate makes it the canonical comparison anchor.
                    </Text>
                  )}
                  {showPromote ? (
                    <PromoteForm
                      candidate={candidate}
                      wouldReplace={wouldReplace}
                      errorMessage={errorMessage}
                      onCancel={() => {
                        setShowPromote(false);
                        setErrorMessage(undefined);
                      }}
                      onSubmit={(input) => {
                        try {
                          promoteCandidate(candidate.candidate_id, input);
                          setShowPromote(false);
                          setErrorMessage(undefined);
                        } catch (error) {
                          setErrorMessage(
                            error instanceof Error ? error.message : 'Failed to promote.',
                          );
                        }
                      }}
                    />
                  ) : (
                    <Button
                      kind="primary"
                      onClick={() => {
                        setErrorMessage(undefined);
                        setShowPromote(true);
                      }}
                    >
                      <Trophy />
                      Promote to Benchmark
                    </Button>
                  )}
                </Stack>
              </Panel>
            )}
            {candidate.is_benchmark && <BenchmarkDetailCard candidate={candidate} />}
          </Stack>
        </Grid>
      </Stack>
    </AccessibleTitle>
  );
};

// ---------------------------------------------------------------------------
// Cards
// ---------------------------------------------------------------------------

interface CandidateMetadataCardProps {
  candidate: Candidate;
  workspace: string;
  groupName?: string;
}

const CandidateMetadataCard: FC<CandidateMetadataCardProps> = ({
  candidate,
  workspace,
  groupName,
}) => (
  <Panel elevation="high" slotHeading="Configuration">
    <Grid className="grid-cols-2 gap-density-lg">
      <KV label="Agent name" value={candidate.agent_name} />
      <KV label="Agent version" value={candidate.agent_version} mono />
      <KV
        label="Dataset"
        value={`${candidate.dataset_id}${candidate.dataset_version ? ` · ${candidate.dataset_version}` : ''}`}
      />
      <KV
        label="Experiment Group"
        value={
          candidate.experiment_group_id ? (
            <Link
              to={getExperimentGroupRoute(workspace, candidate.experiment_group_id)}
              className="no-underline text-accent"
            >
              {groupName ?? candidate.experiment_group_id}
            </Link>
          ) : (
            'None'
          )
        }
      />
      <KV label="Evaluation Runs" value={candidate.run_count.toString()} />
      <KV label="Created" value={formatAbsoluteTimestamp(candidate.created_at)} />
    </Grid>
    {candidate.producer_metadata && (
      <Stack gap="density-sm" className="mt-density-lg">
        <Text kind="body/regular/xs" className="text-secondary uppercase">
          Producer metadata
        </Text>
        <Flex gap="density-xs" wrap="wrap">
          {Object.entries(candidate.producer_metadata).map(([k, v]) => (
            <Badge key={k} kind="outline">
              {k}: {String(v)}
            </Badge>
          ))}
        </Flex>
      </Stack>
    )}
  </Panel>
);

const CandidateScoresCard: FC<{ candidate: Candidate }> = ({ candidate }) => (
  <Panel elevation="high" slotHeading="Aggregate scores">
    <Stack gap="density-xs" className="mb-density-md">
      <Text kind="body/regular/xs" className="text-secondary">
        Means across {candidate.run_count} Evaluation Runs.
      </Text>
    </Stack>
    <Grid className="grid-cols-2 md:grid-cols-3 gap-density-lg">
      {candidate.evaluator_scores.map((score) => (
        <Stack key={score.evaluator_name} gap="density-xxs">
          <Text kind="body/regular/xs" className="text-secondary uppercase">
            {score.evaluator_name}
          </Text>
          <Text kind="title/md">{formatScore(score.mean, score.evaluator_name)}</Text>
          <Text kind="body/regular/xs" className="text-secondary">
            n={score.n_runs}
          </Text>
        </Stack>
      ))}
    </Grid>
  </Panel>
);

const BenchmarkDetailCard: FC<{ candidate: Candidate }> = ({ candidate }) => (
  <Panel elevation="high" slotHeading="Benchmark details">
    <Stack gap="density-md">
      <KV
        label="Slug"
        value={
          <Text kind="body/regular/sm" className="font-mono">
            {candidate.benchmark_slug}
          </Text>
        }
      />
      <KV label="Name" value={candidate.benchmark_name ?? ''} />
      {candidate.benchmark_description && (
        <KV label="Description" value={candidate.benchmark_description} />
      )}
      {candidate.benchmark_promoted_at && (
        <KV label="Promoted at" value={formatAbsoluteTimestamp(candidate.benchmark_promoted_at)} />
      )}
      {candidate.benchmark_promoted_via && (
        <KV
          label="Promoted via"
          value={
            <Flex align="center" gap="density-xs">
              <Badge kind="outline">{candidate.benchmark_promoted_via}</Badge>
              {candidate.benchmark_promoted_by && (
                <Text kind="body/regular/xs" className="text-secondary">
                  by {candidate.benchmark_promoted_by}
                </Text>
              )}
            </Flex>
          }
        />
      )}
    </Stack>
  </Panel>
);

const KV: FC<{ label: string; value: React.ReactNode; mono?: boolean }> = ({
  label,
  value,
  mono,
}) => (
  <Stack gap="density-xxs">
    <Text kind="body/regular/xs" className="text-secondary uppercase">
      {label}
    </Text>
    <Text kind="body/regular/sm" className={mono ? 'font-mono break-all' : ''}>
      {value}
    </Text>
  </Stack>
);

// ---------------------------------------------------------------------------
// Inline Promote form (expands within the right-rail panel)
// ---------------------------------------------------------------------------

interface PromoteFormProps {
  candidate: Candidate;
  wouldReplace?: Candidate;
  errorMessage?: string;
  onCancel: () => void;
  onSubmit: (input: { slug: string; name: string; description?: string }) => void;
}

const PromoteForm: FC<PromoteFormProps> = ({
  candidate,
  wouldReplace,
  errorMessage,
  onCancel,
  onSubmit,
}) => {
  const defaultSlug = wouldReplace?.benchmark_slug ?? slugify(candidate.candidate_id);
  const defaultName =
    wouldReplace?.benchmark_name ?? `${candidate.agent_name} — ${candidate.dataset_id}`;
  const [slug, setSlug] = useState(defaultSlug);
  const [name, setName] = useState(defaultName);
  const [description, setDescription] = useState('');

  return (
    <Stack gap="density-md" className="border-t border-base pt-density-md">
      {wouldReplace && (
        <Panel elevation="low">
          <Flex align="start" gap="density-sm">
            <ShieldAlert className="text-warning shrink-0 mt-density-xxs" size={18} />
            <Stack gap="density-xxs">
              <Text kind="label/bold/sm">Replacing existing Benchmark</Text>
              <Text kind="body/regular/sm" className="text-secondary">
                {wouldReplace.benchmark_name ?? wouldReplace.candidate_id} (
                {wouldReplace.agent_version}) will be demoted.
              </Text>
            </Stack>
          </Flex>
        </Panel>
      )}
      <FormField name="benchmark-slug" slotLabel="Slug">
        <TextInput value={slug} onValueChange={setSlug} placeholder="e.g. wiki-main" />
      </FormField>
      <FormField name="benchmark-name" slotLabel="Name">
        <TextInput value={name} onValueChange={setName} />
      </FormField>
      <FormField name="benchmark-description" slotLabel="Description (optional)">
        <TextArea
          value={description}
          onValueChange={setDescription}
          placeholder="What does this Benchmark represent?"
          attributes={{ TextAreaElement: { rows: 3 } }}
        />
      </FormField>
      {errorMessage && (
        <Text kind="body/regular/sm" className="text-danger">
          {errorMessage}
        </Text>
      )}
      <Flex justify="end" gap="density-sm">
        <Button kind="tertiary" onClick={onCancel}>
          <X />
          Cancel
        </Button>
        <Button
          kind="primary"
          disabled={!slug.trim() || !name.trim()}
          onClick={() =>
            onSubmit({
              slug: slug.trim(),
              name: name.trim(),
              description: description.trim() || undefined,
            })
          }
        >
          <Trophy />
          Confirm promotion
        </Button>
      </Flex>
    </Stack>
  );
};

// ---------------------------------------------------------------------------
// Inline Demote confirmation
// ---------------------------------------------------------------------------

interface DemoteConfirmationProps {
  candidate: Candidate;
  onCancel: () => void;
  onConfirm: () => void;
}

const DemoteConfirmation: FC<DemoteConfirmationProps> = ({ candidate, onCancel, onConfirm }) => (
  <Stack gap="density-md" className="border-t border-base pt-density-md">
    <Text kind="body/regular/sm">
      {candidate.agent_name} × {candidate.dataset_id} will have no Benchmark until another Candidate
      is promoted. Slug{' '}
      <span className="font-mono font-semibold">{candidate.benchmark_slug}</span> will be cleared.
    </Text>
    <Flex justify="end" gap="density-sm">
      <Button kind="tertiary" onClick={onCancel}>
        <X />
        Cancel
      </Button>
      <Button kind="primary" onClick={onConfirm}>
        <Undo2 />
        Confirm demotion
      </Button>
    </Flex>
  </Stack>
);

// ---------------------------------------------------------------------------
// Utils
// ---------------------------------------------------------------------------

const slugify = (input: string): string =>
  input
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');

const formatScore = (value: number, evaluatorName: string): string => {
  if (evaluatorName.toLowerCase().includes('latency')) {
    return `${value.toFixed(0)} ms`;
  }
  if (evaluatorName.toLowerCase().includes('cost')) {
    return `$${value.toFixed(3)}`;
  }
  return value.toFixed(3);
};
