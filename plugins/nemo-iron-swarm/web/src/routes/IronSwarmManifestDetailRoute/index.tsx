// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useUploadBenignSuiteFileset, useUploadHitlogFileset } from '@iron-swarm/api/filesets';
import { BenignInterviewCard } from '@iron-swarm/components/BenignInterviewCard';
import { BenignSuiteTable } from '@iron-swarm/components/BenignSuiteTable';
import type { SuiteRow } from '@iron-swarm/components/hitlTypes';
import { InterviewPanel } from '@iron-swarm/components/InterviewPanel';
import { ModelGroupFields } from '@iron-swarm/components/ModelGroupFields';
import { ReconChecklist } from '@iron-swarm/components/ReconChecklist';
import { ReviewPanel } from '@iron-swarm/components/ReviewPanel';
import { TargetPanel } from '@iron-swarm/components/TargetPanel';
import { useGenerateBenignSuite } from '@iron-swarm/components/useGenerateBenignSuite';
import { useRunWarGame } from '@iron-swarm/components/useRunWarGame';
import {
  getIronSwarmGetManifestQueryKey,
  useIronSwarmGetManifest,
  useIronSwarmGetModelConfigDefaults,
  useIronSwarmListRuns,
  useIronSwarmRefreshManifest,
  useIronSwarmUpdateManifest,
} from '@iron-swarm/generated/api';
import type { IronSwarmRun, WarGameModels } from '@iron-swarm/generated/schema';
import { useBreadcrumbs, useNotify, useToast, useWorkspace } from '@iron-swarm/host';
import { getIronSwarmManifestListRoute, getIronSwarmRunListRoute } from '@iron-swarm/paths';
import {
  BENIGN_SOURCE_LABEL,
  INTENSITY_LABEL,
  REPLAY_SOURCE_LABEL,
} from '@iron-swarm/routes/IronSwarmManifestDetailRoute/constants';
import type {
  AttackIntensity,
  BenignSource,
  DefenderSelection,
  ReplaySource,
} from '@iron-swarm/routes/IronSwarmManifestDetailRoute/types';
import { toRequestsCsv } from '@iron-swarm/routes/IronSwarmManifestDetailRoute/utils';
import { FEEDBACK } from '@iron-swarm/theme';
import { AccessibleTitle, AccordionSection, ConfirmationModal, FileUpload, FormModal, triggerDownload } from '@nemo/common';
import {
  AccordionRoot,
  Button,
  Checkbox,
  Flex,
  FormField,
  PageHeader,
  Panel,
  SegmentedControl,
  SelectContent,
  SelectItem,
  SelectListbox,
  SelectRoot,
  SelectTrigger,
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
  const [port, setPort] = useState('');
  const [defenders, setDefenders] = useState<DefenderSelection>({
    guardrails: true,
    openshell: true,
  });
  const [intensity, setIntensity] = useState<AttackIntensity>('standard');
  const [rounds, setRounds] = useState('1');
  const [models, setModels] = useState<WarGameModels>({});
  const { data: modelDefaults } = useIronSwarmGetModelConfigDefaults(workspace, { query: {} });
  // The launch dialog holds per-run config + attack mode. Config seeds from the manifest default and is
  // sent as a per-run override on the spec — launching never rewrites the manifest ("Save as default" does).
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [mode, setMode] = useState<'live' | 'replay'>('live');
  const [replaySource, setReplaySource] = useState<ReplaySource>('last');
  const [hitlogFile, setHitlogFile] = useState<File | undefined>();
  const [hitlogFileset, setHitlogFileset] = useState<string | undefined>();
  const [benignSource, setBenignSource] = useState<BenignSource>('manifest');
  const [benignFile, setBenignFile] = useState<File | undefined>();
  const [benignFileset, setBenignFileset] = useState<string | undefined>();
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

  // "Last run" replay source: the newest prior run of THIS manifest that saved a hitlog fileset.
  const { data: runsData } = useIronSwarmListRuns(
    workspace,
    { sort: '-created_at', page_size: 20, filter: { manifest_id: ironSwarmManifestName } },
    { query: { enabled: runDialogOpen && mode === 'replay' && replaySource === 'last' } }
  );
  const lastHitlogFileset = ((runsData?.data ?? []) as IronSwarmRun[]).find(
    (r) => r.hitlog_fileset
  )?.hitlog_fileset;

  const uploadHitlog = useUploadHitlogFileset();
  const onHitlogDrop = async (accepted: File[]): Promise<void> => {
    const file = accepted[0];
    if (!file) return;
    setHitlogFile(file);
    setHitlogFileset(undefined);
    try {
      setHitlogFileset(
        await uploadHitlog.mutateAsync({ workspace, manifestName: ironSwarmManifestName, file })
      );
    } catch {
      toast.error('Failed to upload the hitlog file.');
    }
  };

  const uploadBenign = useUploadBenignSuiteFileset();
  const onBenignDrop = async (accepted: File[]): Promise<void> => {
    const file = accepted[0];
    if (!file) return;
    setBenignFile(file);
    setBenignFileset(undefined);
    try {
      setBenignFileset(
        await uploadBenign.mutateAsync({ workspace, manifestName: ironSwarmManifestName, file })
      );
    } catch {
      toast.error('Failed to upload the benign suite file.');
    }
  };

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
  const buildRunConfig = () => {
    const keys = (['guardrails', 'openshell'] as const).filter((k) => defenders[k]);
    return {
      defenders: keys,
      attack_intensity: intensity,
      rounds: Number(rounds) || 1,
      models,
      ...(port ? { port: Number(port) } : {}),
    };
  };

  const openRunDialog = () => {
    // Attacking replays the benign suite, so require one — the Generate action is how you make it.
    if (suite.length === 0) {
      toast.error('No benign suite yet — generate it first, then run the war-game.');
      return;
    }
    // Seed the dialog's config from the manifest default here rather than in an effect: keying off
    // `manifest` meant any refetch while the dialog was open (e.g. "Save as default" invalidating
    // the query) wiped whatever the user had typed. Per-run tweaks stay ephemeral either way.
    setPort(manifest?.port ? String(manifest.port) : '');
    // Empty stored list means iron-swarm defaults (all defenders) — reflect that as both checked.
    const saved = manifest?.defenders ?? [];
    setDefenders(
      saved.length
        ? { guardrails: saved.includes('guardrails'), openshell: saved.includes('openshell') }
        : { guardrails: true, openshell: true }
    );
    setIntensity((manifest?.attack_intensity as AttackIntensity | undefined) ?? 'standard');
    setRounds(manifest?.rounds ? String(manifest.rounds) : '1');
    setModels(manifest?.models ?? {});
    setMode('live');
    setReplaySource('last');
    setHitlogFile(undefined);
    setHitlogFileset(undefined);
    setBenignSource('manifest');
    setBenignFile(undefined);
    setBenignFileset(undefined);
    setRunDialogOpen(true);
  };

  // Dialog submit: launch with per-run config overrides. Never writes the manifest.
  const start = () => {
    const cfg = buildRunConfig();
    if (cfg.defenders.length === 0) {
      toast.error('Select at least one defender.');
      return;
    }
    let replay_hitlog_fileset: string | undefined;
    if (mode === 'replay') {
      replay_hitlog_fileset = replaySource === 'upload' ? hitlogFileset : lastHitlogFileset;
      if (!replay_hitlog_fileset) {
        toast.error(
          replaySource === 'upload'
            ? 'Upload a hitlog file to replay first.'
            : 'No previous run of this manifest has recorded hits — run a live attack once, or upload a hitlog.'
        );
        return;
      }
    }
    // Uploaded benign suite (if chosen) overrides the manifest's suite for this run.
    if (benignSource === 'upload' && !benignFileset) {
      toast.error('Upload a benign suite CSV first.');
      return;
    }
    const benign_suite_fileset = benignSource === 'upload' ? benignFileset : undefined;
    runWarGame.mutate({
      workspace,
      data: {
        spec: {
          manifest_id: ironSwarmManifestName,
          driver: 'service',
          stop_after_synth: false,
          ...cfg,
          ...(replay_hitlog_fileset ? { replay_hitlog_fileset } : {}),
          ...(benign_suite_fileset ? { benign_suite_fileset } : {}),
        },
      },
    });
    setRunDialogOpen(false);
  };

  // Persist the current dialog config as the manifest's default (no launch).
  const saveAsDefault = () => {
    const cfg = buildRunConfig();
    if (cfg.defenders.length === 0) {
      toast.error('Select at least one defender.');
      return;
    }
    updateManifest.mutate({ workspace, name: ironSwarmManifestName, data: cfg });
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

      <FormModal
        open={runDialogOpen}
        title="Start war-game"
        submitButtonText="Start"
        loading={runWarGame.isPending}
        submitDisabled={
          (mode === 'replay' &&
            (replaySource === 'upload'
              ? !hitlogFileset || uploadHitlog.isPending
              : !lastHitlogFileset)) ||
          (benignSource === 'upload' && (!benignFileset || uploadBenign.isPending))
        }
        onSubmit={(e) => {
          e.preventDefault();
          start();
        }}
        onClose={() => setRunDialogOpen(false)}
      >
        <Stack gap="density-md">
          <Text kind="body/regular/sm" className="text-subtle">
            Config applies to this run only. Use “Save as default” to make it the manifest baseline.
          </Text>

          <FormField
            name="port"
            slotLabel="Victim Port"
            slotHelp="Port the war-game targets on the victim agent."
          >
            <TextInput
              value={port}
              onChange={(e) => setPort(e.target.value.replace(/[^0-9]/g, ''))}
            />
          </FormField>

          <Stack gap="density-sm">
            <Text kind="body/semibold/sm" className="uppercase tracking-wide text-subtle">
              Defenders
            </Text>
            <Flex align="center" gap="density-sm">
              <Checkbox
                checked={defenders.guardrails}
                onCheckedChange={(c) => setDefenders((d) => ({ ...d, guardrails: c === true }))}
                attributes={{ CheckboxInput: { 'aria-label': 'Guardrails defender' } }}
              />
              <Text kind="body/regular/sm">Guardrails defender</Text>
            </Flex>
            <Flex align="center" gap="density-sm">
              <Checkbox
                checked={defenders.openshell}
                onCheckedChange={(c) => setDefenders((d) => ({ ...d, openshell: c === true }))}
                attributes={{ CheckboxInput: { 'aria-label': 'OpenShell policy defender' } }}
              />
              <Text kind="body/regular/sm">OpenShell policy defender</Text>
            </Flex>
          </Stack>

          <FormField
            name="intensity"
            slotLabel="Attack Intensity"
            slotHelp="How hard the garak attacker probes the agent — more probes and generations at higher levels."
          >
            {/* The trigger echoes the raw value, so use capitalized values (== display) and lowercase for the API. */}
            <SelectRoot
              value={INTENSITY_LABEL[intensity]}
              onValueChange={(v: string) => setIntensity(v.toLowerCase() as AttackIntensity)}
            >
              <SelectTrigger className="w-full" placeholder="Select intensity" />
              <SelectContent className="w-(--radix-popper-anchor-width)">
                <SelectListbox>
                  <SelectItem value="Light">Light</SelectItem>
                  <SelectItem value="Standard">Standard</SelectItem>
                  <SelectItem value="Thorough">Thorough</SelectItem>
                </SelectListbox>
              </SelectContent>
            </SelectRoot>
          </FormField>

          <FormField
            name="rounds"
            slotLabel="Rounds"
            slotHelp="Iterative attack → defend → validate → redeploy cycles. More rounds go deeper but take longer."
          >
            <TextInput
              value={rounds}
              onChange={(e) => setRounds(e.target.value.replace(/[^0-9]/g, ''))}
            />
          </FormField>

          <AccordionRoot>
            <AccordionSection value="models" title="Models (optional)">
              <ModelGroupFields
                value={models}
                onChange={setModels}
                workspace={workspace}
                defaults={modelDefaults}
              />
            </AccordionSection>
          </AccordionRoot>

          <FormField
            name="benignSource"
            slotLabel="Benign suite"
            slotHelp="The benign requests replayed after hardening to confirm the agent still works. Defaults to the manifest's suite; upload a requests.csv to override it for this run."
          >
            <SelectRoot
              value={BENIGN_SOURCE_LABEL[benignSource]}
              onValueChange={(v: string) =>
                setBenignSource(v === BENIGN_SOURCE_LABEL.upload ? 'upload' : 'manifest')
              }
            >
              <SelectTrigger className="w-full" placeholder="Select benign suite" />
              <SelectContent className="w-(--radix-popper-anchor-width)">
                <SelectListbox>
                  <SelectItem value={BENIGN_SOURCE_LABEL.manifest}>
                    {BENIGN_SOURCE_LABEL.manifest}
                  </SelectItem>
                  <SelectItem value={BENIGN_SOURCE_LABEL.upload}>
                    {BENIGN_SOURCE_LABEL.upload}
                  </SelectItem>
                </SelectListbox>
              </SelectContent>
            </SelectRoot>
          </FormField>

          {benignSource === 'upload' ? (
            <FileUpload
              label="Benign suite"
              accept={{ 'text/csv': ['.csv'] }}
              multiple={false}
              files={benignFile ? [benignFile] : []}
              onDropAccepted={(accepted) => void onBenignDrop(accepted)}
              onRemoveFile={() => {
                setBenignFile(undefined);
                setBenignFileset(undefined);
              }}
              helperText={
                uploadBenign.isPending
                  ? 'Uploading…'
                  : benignFileset
                    ? 'Uploaded — will override the manifest suite for this run.'
                    : 'A benign requests.csv (tool,payload,label,rationale,persona).'
              }
            />
          ) : null}

          <FormField
            name="mode"
            slotLabel="Attack mode"
            slotHelp="Live runs a fresh garak attack; Replay skips it and replays recorded hits against the defended agent."
          >
            <SegmentedControl
              className="w-full"
              value={mode}
              onValueChange={(v) => setMode(v as 'live' | 'replay')}
              items={[
                { value: 'live', children: 'Live attack' },
                { value: 'replay', children: 'Replay recorded hits' },
              ]}
            />
          </FormField>

          {mode === 'replay' ? (
            <>
              <FormField name="replaySource" slotLabel="Hits to replay">
                <SelectRoot
                  value={REPLAY_SOURCE_LABEL[replaySource]}
                  onValueChange={(v: string) =>
                    setReplaySource(v === REPLAY_SOURCE_LABEL.upload ? 'upload' : 'last')
                  }
                >
                  <SelectTrigger className="w-full" placeholder="Select hits to replay" />
                  <SelectContent className="w-(--radix-popper-anchor-width)">
                    <SelectListbox>
                      <SelectItem value={REPLAY_SOURCE_LABEL.last}>
                        {REPLAY_SOURCE_LABEL.last}
                      </SelectItem>
                      <SelectItem value={REPLAY_SOURCE_LABEL.upload}>
                        {REPLAY_SOURCE_LABEL.upload}
                      </SelectItem>
                    </SelectListbox>
                  </SelectContent>
                </SelectRoot>
              </FormField>

              {replaySource === 'last' ? (
                <Text
                  kind="body/regular/sm"
                  className={lastHitlogFileset ? 'text-subtle' : undefined}
                  style={lastHitlogFileset ? undefined : { color: FEEDBACK.warning }}
                >
                  {lastHitlogFileset
                    ? "Replays this manifest's most recent recorded hits."
                    : 'No previous run of this manifest has recorded hits — run a live attack once, or upload a hitlog.'}
                </Text>
              ) : (
                <FileUpload
                  label="Hitlog"
                  accept={{ 'application/jsonl': ['.jsonl', '.json'] }}
                  multiple={false}
                  files={hitlogFile ? [hitlogFile] : []}
                  onDropAccepted={(accepted) => void onHitlogDrop(accepted)}
                  onRemoveFile={() => {
                    setHitlogFile(undefined);
                    setHitlogFileset(undefined);
                  }}
                  helperText={
                    uploadHitlog.isPending
                      ? 'Uploading…'
                      : hitlogFileset
                        ? 'Uploaded — ready to replay.'
                        : 'A garak hitlog (.jsonl) recording the attack hits to replay.'
                  }
                />
              )}
            </>
          ) : null}

          <Flex>
            <Button
              kind="tertiary"
              type="button"
              disabled={updateManifest.isPending}
              onClick={saveAsDefault}
            >
              Save as default
            </Button>
          </Flex>
        </Stack>
      </FormModal>
    </AccessibleTitle>
  );
};
