// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { BenignInterviewCard } from '@iron-swarm/components/BenignInterviewCard';
import { BenignSuiteTable } from '@iron-swarm/components/BenignSuiteTable';
import type { SuiteRow } from '@iron-swarm/components/hitlTypes';
import { InterviewPanel } from '@iron-swarm/components/InterviewPanel';
import { ReconChecklist } from '@iron-swarm/components/ReconChecklist';
import { ReviewPanel } from '@iron-swarm/components/ReviewPanel';
import {
  RunWarGameDialog,
  type RunConfig,
  type RunLaunch,
} from '@iron-swarm/components/RunWarGameDialog';
import { TargetPanel } from '@iron-swarm/components/TargetPanel';
import { useGenerateBenignSuite } from '@iron-swarm/components/useGenerateBenignSuite';
import { useRunWarGame } from '@iron-swarm/components/useRunWarGame';
import {
  getIronSwarmGetManifestQueryKey,
  useIronSwarmGetManifest,
  useIronSwarmRefreshManifest,
  useIronSwarmUpdateManifest,
} from '@iron-swarm/generated/api';
import { useBreadcrumbs, useNotify, useToast, useWorkspace } from '@iron-swarm/host';
import { getIronSwarmManifestListRoute, getIronSwarmRunListRoute } from '@iron-swarm/paths';
import { toRequestsCsv } from '@iron-swarm/routes/IronSwarmManifestDetailRoute/utils';
import { AccessibleTitle, AccordionSection, ConfirmationModal, FormModal, triggerDownload } from '@nemo/common';
import {
  AccordionRoot,
  Button,
  Flex,
  FormField,
  PageHeader,
  Panel,
  Stack,
  Text,
  TextInput,
} from '@nvidia/foundations-react-core';
import { useQueryClient } from '@tanstack/react-query';
import { FC, useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router';

export const IronSwarmManifestDetailRoute: FC = () => {
  const workspace = useWorkspace();
  const { ironSwarmManifestName = '' } = useParams<{ ironSwarmManifestName: string }>();
  const toast = useToast();
  const notify = useNotify();
  const queryClient = useQueryClient();

  useBreadcrumbs({
    items: [
      { href: getIronSwarmRunListRoute(workspace), slotLabel: 'Iron Swarm' },
      { href: getIronSwarmManifestListRoute(workspace), slotLabel: 'Manifests' },
      { slotLabel: ironSwarmManifestName },
    ],
  });

  const { data: manifest, isLoading } = useIronSwarmGetManifest(workspace, ironSwarmManifestName, {
    query: { enabled: Boolean(ironSwarmManifestName) },
  });

  // Seed the editable state once the manifest loads. The `seeded` ref below is what keeps this
  // one-shot — the query does get refetched, since saving the manifest invalidates its key.
  const [suite, setSuite] = useState<SuiteRow[]>([]);
  // The launch dialog holds per-run config + attack mode. Config seeds from the manifest default and is
  // sent as a per-run override on the spec — launching never rewrites the manifest ("Save as default" does).
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const seeded = useRef(false);
  useEffect(() => {
    if (!manifest || seeded.current) return;
    seeded.current = true;
    setSuite(
      (manifest.benign_suite ?? []).map((row) => ({
        tool: row.tool ?? '',
        payload: row.payload ?? '',
        label: row.label,
        persona: row.persona,
        rationale: row.rationale,
      }))
    );
  }, [manifest]);

  const updateManifest = useIronSwarmUpdateManifest({
    mutation: {
      onSuccess: () => {
        toast.success('Manifest saved.');
        queryClient.invalidateQueries({
          queryKey: getIronSwarmGetManifestQueryKey(workspace, ironSwarmManifestName),
        });
      },
      onError: () => toast.error('Failed to save the manifest.'),
    },
  });
  const runWarGame = useRunWarGame(workspace);
  const clearManifest = useIronSwarmUpdateManifest();
  const [confirmClear, setConfirmClear] = useState(false);
  const [confirmRefresh, setConfirmRefresh] = useState(false);
  const [envDialogOpen, setEnvDialogOpen] = useState(false);
  const [envDraft, setEnvDraft] = useState('');

  // Generation runs on the manifest (the suite is a manifest asset). On completion, re-seed the editor + csv
  // view from the freshly saved suite.
  const onGenerated = useCallback(() => {
    toast.success('Benign suite generated.');
    queryClient.invalidateQueries({
      queryKey: getIronSwarmGetManifestQueryKey(workspace, ironSwarmManifestName),
    });
    seeded.current = false;
  }, [toast, queryClient, workspace, ironSwarmManifestName]);
  const gen = useGenerateBenignSuite(workspace, ironSwarmManifestName, onGenerated);

  const clearSuite = async (): Promise<boolean> => {
    try {
      await clearManifest.mutateAsync({
        workspace,
        name: ironSwarmManifestName,
        data: { benign_suite: [] },
      });
      setSuite([]);
      queryClient.invalidateQueries({
        queryKey: getIronSwarmGetManifestQueryKey(workspace, ironSwarmManifestName),
      });
      return true;
    } catch {
      return false;
    }
  };

  // env is stored as a map but edited as `KEY=VALUE, KEY2=VALUE2` — one text field beats a
  // key/value grid for the handful of entries an agent actually needs.
  const openEnvDialog = useCallback(() => {
    setEnvDraft(
      Object.entries(manifest?.env ?? {})
        .map(([key, value]) => `${key}=${value}`)
        .join(', ')
    );
    setEnvDialogOpen(true);
  }, [manifest?.env]);

  const saveEnv = async (): Promise<void> => {
    const env: Record<string, string> = {};
    for (const entry of envDraft.split(',').map((part) => part.trim())) {
      const at = entry.indexOf('=');
      if (at > 0) env[entry.slice(0, at).trim()] = entry.slice(at + 1).trim();
    }
    try {
      await clearManifest.mutateAsync({ workspace, name: ironSwarmManifestName, data: { env } });
      queryClient.invalidateQueries({
        queryKey: getIronSwarmGetManifestQueryKey(workspace, ironSwarmManifestName),
      });
      toast.success('Environment variables saved.');
      setEnvDialogOpen(false);
    } catch {
      toast.error('Failed to save the environment variables.');
    }
  };

  const refreshManifest = useIronSwarmRefreshManifest();
  // Manifests are frozen targets, so agent edits only land here deliberately. Confirmed because it
  // changes what the next run attacks.
  const refreshTarget = async (): Promise<boolean> => {
    try {
      await refreshManifest.mutateAsync({ workspace, name: ironSwarmManifestName });
      queryClient.invalidateQueries({
        queryKey: getIronSwarmGetManifestQueryKey(workspace, ironSwarmManifestName),
      });
      return true;
    } catch {
      return false;
    }
  };

  const downloadCsv = () => {
    // Keep the Blob explicit so its text/csv type survives into the download.
    triggerDownload(
      new Blob([toRequestsCsv(suite)], { type: 'text/csv' }),
      `${ironSwarmManifestName}-requests.csv`
    );
  };

  // The table edits the saved suite directly: each row save/delete/add persists immediately (auto-save).
  const persistSuite = (rows: SuiteRow[]) => {
    setSuite(rows);
    updateManifest.mutate({
      workspace,
      name: ironSwarmManifestName,
      // The wire shape is string-valued records; coerce the optional SuiteRow fields to strings.
      data: {
        benign_suite: rows.map((r) => ({
          tool: r.tool,
          payload: r.payload,
          label: r.label ?? '',
          persona: r.persona ?? '',
          rationale: r.rationale ?? '',
        })),
      },
    });
  };

  // The per-run config the dialog collects — sent as spec overrides, or saved to the manifest as defaults.
  const openRunDialog = () => {
    // Attacking replays the benign suite, so require one — the Generate action is how you make it.
    if (suite.length === 0) {
      toast.error('No benign suite yet — generate it first, then run the war-game.');
      return;
    }
    setRunDialogOpen(true);
  };

  // Launch with per-run overrides; never writes the manifest. The dialog has already validated.
  const start = (launch: RunLaunch) => {
    runWarGame.mutate({
      workspace,
      data: {
        spec: {
          manifest_id: ironSwarmManifestName,
          driver: 'service',
          stop_after_synth: false,
          ...launch,
        },
      },
    });
    setRunDialogOpen(false);
  };

  // Persist the dialog's config as the manifest's default (no launch).
  const saveAsDefault = (config: RunConfig) => {
    updateManifest.mutate({ workspace, name: ironSwarmManifestName, data: config });
  };

  return (
    <AccessibleTitle title={`Iron Swarm manifest — ${ironSwarmManifestName}`}>
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading={ironSwarmManifestName}
          slotDescription={manifest?.agent ? `Hardens ${manifest.agent}` : undefined}
          slotActions={
            <Flex gap="density-sm">
              <Button kind="secondary" disabled={gen.active} onClick={() => gen.start()}>
                {gen.active
                  ? 'Generating…'
                  : suite.length
                    ? 'Regenerate benign suite'
                    : 'Generate benign suite'}
              </Button>
              <Button color="brand" disabled={runWarGame.isPending} onClick={openRunDialog}>
                Run war-game
              </Button>
            </Flex>
          }
        />

        {gen.active ? (
          <Panel>
            <Stack gap="density-lg" padding="density-lg">
              <Text kind="body/semibold/md">Generating benign suite</Text>
              <Text kind="body/regular/sm" className="text-subtle">
                {gen.interview
                  ? 'Answer the interview to shape the benign test suite.'
                  : gen.review
                    ? 'Review and approve the generated requests.'
                    : gen.starting
                      ? 'Starting the sandbox and probing the agent…'
                      : 'Synthesizing the benign suite…'}
              </Text>
              <ReconChecklist
                steps={gen.recon}
                busy={!gen.interview && !gen.review}
                activity={gen.activity}
              />
              {gen.interview ? (
                <InterviewPanel
                  // Remount per round: the panel seeds its answers on mount, so without this a
                  // round that arrives while the panel stays mounted reuses the previous answers.
                  key={gen.interview.round}
                  prompt={gen.interview}
                  loading={gen.isResponding}
                  onSubmit={gen.submitInterview}
                />
              ) : gen.review ? (
                <ReviewPanel
                  key={gen.review.round}
                  suite={gen.review.suite}
                  loading={gen.isResponding}
                  onSubmit={gen.submitReview}
                />
              ) : null}
            </Stack>
          </Panel>
        ) : null}

        {manifest ? (
          <TargetPanel
            manifest={manifest}
            onRefresh={() => setConfirmRefresh(true)}
            refreshing={refreshManifest.isPending}
            onEditEnv={openEnvDialog}
          />
        ) : null}

        <Panel>
          <Stack gap="density-lg" padding="density-lg">
            <Flex className="items-center justify-between">
              <Text kind="body/semibold/md">Benign suite (requests.csv)</Text>
              <Button
                kind="secondary"
                size="small"
                disabled={suite.length === 0}
                onClick={downloadCsv}
              >
                Download
              </Button>
            </Flex>
            <Text kind="body/regular/sm" className="text-subtle">
              The benign requests replayed after hardening to confirm the agent still works. Edit a
              row inline or generate the suite — changes save automatically.
            </Text>
            {isLoading && !manifest ? (
              <Text kind="body/regular/md" className="text-subtle">
                Loading…
              </Text>
            ) : (
              <BenignSuiteTable
                value={suite}
                onChange={persistSuite}
                disabled={updateManifest.isPending}
              />
            )}
            <Flex>
              <Button
                kind="tertiary"
                color="danger"
                disabled={suite.length === 0 || clearManifest.isPending}
                onClick={() => setConfirmClear(true)}
              >
                Clear benign requests
              </Button>
            </Flex>
          </Stack>
        </Panel>

        {manifest?.benign_interview && manifest.benign_interview.length > 0 ? (
          <AccordionRoot multiple>
            <AccordionSection
              value="interview"
              title={`Interview Q&A (${manifest.benign_interview.length})`}
            >
              <Stack gap="density-md">
                <Text kind="body/regular/sm" className="text-subtle">
                  Your answers from the last benign-suite generation — the context that shaped this
                  suite.
                </Text>
                <BenignInterviewCard interview={manifest.benign_interview} />
              </Stack>
            </AccordionSection>
          </AccordionRoot>
        ) : null}
      </Stack>

      <ConfirmationModal
        onNotify={notify}
        open={confirmClear}
        onClose={() => setConfirmClear(false)}
        title="Clear benign requests?"
        description="This removes every benign request from this manifest. You'll need to regenerate the suite before the next run."
        submitButtonText="Clear requests"
        submitButtonColor="danger"
        successText="Benign requests cleared."
        errorText="Failed to clear the benign requests."
        onConfirm={clearSuite}
      />

      <FormModal
        open={envDialogOpen}
        title="Edit Environment Variables"
        submitButtonText="Save"
        loading={clearManifest.isPending}
        onSubmit={(e) => {
          e.preventDefault();
          void saveEnv();
        }}
        onClose={() => setEnvDialogOpen(false)}
      >
        <Stack gap="density-md">
          <Text kind="body/regular/sm" className="text-fg-secondary">
            Non-secret settings the agent reads, as comma-separated KEY=VALUE pairs. Credentials
            belong in the manifest&apos;s secrets — values here are stored in plain text.
          </Text>
          <FormField name="env" slotLabel="Environment Variables">
            <TextInput value={envDraft} onChange={(event) => setEnvDraft(event.target.value)} />
          </FormField>
        </Stack>
      </FormModal>

      <ConfirmationModal
        onNotify={notify}
        open={confirmRefresh}
        onClose={() => setConfirmRefresh(false)}
        title={`Refresh ${ironSwarmManifestName}?`}
        description="Re-resolves this manifest against the agent as it is now, so the next run attacks the current agent instead of the one saved here. Your egress, secrets, models, defenders and benign suite are kept."
        submitButtonText="Refresh Target"
        successText="Target refreshed from the agent."
        errorText="Failed to refresh the target."
        onConfirm={refreshTarget}
      />

      <RunWarGameDialog
        open={runDialogOpen}
        onClose={() => setRunDialogOpen(false)}
        workspace={workspace}
        manifestName={ironSwarmManifestName}
        manifest={manifest}
        starting={runWarGame.isPending}
        savingDefault={updateManifest.isPending}
        onStart={start}
        onSaveDefault={saveAsDefault}
      />
    </AccessibleTitle>
  );
};
