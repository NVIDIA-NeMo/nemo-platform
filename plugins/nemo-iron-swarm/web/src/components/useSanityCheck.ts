// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { customFetch } from '@iron-swarm/api/fetcher';
import type { Mitigations } from '@iron-swarm/components/useMitigations';
import {
  ironSwarmDownloadJobResult,
  ironSwarmListRuns,
  useIronSwarmCreateJob,
  useIronSwarmListJobResults,
} from '@iron-swarm/generated/api';
import type { IronSwarmRun } from '@iron-swarm/generated/schema';
import { JOB_POLLING_INTERVAL_MS } from '@nemo/common';
import { useMutation, useQuery } from '@tanstack/react-query';

// The validate-only run writes a `validation` job result: per-item attack/benign verdicts for the scorecard.
const VALIDATION_RESULT = 'validation';
// …and a `composed-workflow` result: the exact workflow YAML it validated, so "Apply to Agent" survives a reload.
const COMPOSED_WORKFLOW_RESULT = 'composed-workflow';

export interface ValidationAttackRow {
  attack_id?: string;
  probe?: string;
  goal?: string;
  prompt_excerpt?: string;
  status?: 'blocked' | 'not_blocked' | 'error';
  confidence?: number;
}

export interface ValidationBenignRow {
  index?: number;
  tool?: string;
  label?: string;
  persona?: string;
  payload_excerpt?: string;
  status?: 'passed' | 'refused' | 'error';
  confidence?: number;
}

export interface ValidationSummary {
  attacks_total: number;
  attacks_blocked: number;
  benign_total: number;
  benign_false_positives: number;
}

export interface ValidationReport {
  attacks: ValidationAttackRow[];
  benign: ValidationBenignRow[];
  summary: ValidationSummary;
}

interface ComposeDefenseResponse {
  workflow_yaml?: string | null;
  policy_yaml?: string | null;
}

// Compose the chosen subset of a run's defenses into deployable workflow + policy YAML (server-side, so the
// same composition feeds the live preview and the sanity-check run). Sends the mitigations the client already
// holds plus the selected ids.
export const useComposeDefense = (workspace: string, runName: string) =>
  useMutation({
    mutationFn: (vars: {
      mitigations: Mitigations;
      selectedDefenseIds: string[];
    }): Promise<ComposeDefenseResponse> =>
      customFetch<ComposeDefenseResponse>({
        url: `/apis/iron-swarm/v2/workspaces/${encodeURIComponent(workspace)}/runs/${encodeURIComponent(runName)}/compose-defense`,
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        data: { mitigations: vars.mitigations, selected_defense_ids: vars.selectedDefenseIds },
      }),
  });

interface SanityCheckSpec {
  manifest_id: string;
  driver: 'service';
  validate_only: true;
  replay_hitlog_fileset: string;
  defense_workflow?: string;
  defense_policy?: string;
  // The harden run this check was launched from — recorded on the sanity run so the report re-attaches on reload.
  source_run: string;
}

// Submit a validate-only war-game: freeze the composed defenses as the victim baseline and replay the
// recorded attacks + benign suite against it. Returns the created job name so the caller can poll its result.
export const useSubmitSanityCheck = (workspace: string) => {
  const createJob = useIronSwarmCreateJob();
  const submit = async (spec: SanityCheckSpec): Promise<string> => {
    // The backend WarGameSpec accepts validate_only/defense_* (added for the sanity check); the generated
    // client type predates them, so pass the spec through the untyped job request field.
    const job = await createJob.mutateAsync({ workspace, data: { spec } as never });
    return job.name;
  };
  return { submit, isPending: createJob.isPending };
};

// Poll the sanity-check job's results until `validation.json` lands, then download + parse it once.
export const useSanityCheckResult = (workspace: string, jobName: string | undefined) => {
  const { data: results } = useIronSwarmListJobResults(workspace, jobName ?? '', {
    query: {
      enabled: Boolean(jobName),
      refetchInterval: (query) =>
        query.state.data?.data?.some((result) => result.name === VALIDATION_RESULT)
          ? false
          : JOB_POLLING_INTERVAL_MS,
    },
  });
  const hasReport = Boolean(results?.data?.some((result) => result.name === VALIDATION_RESULT));

  const query = useQuery({
    queryKey: ['iron-swarm-validation', workspace, jobName],
    enabled: hasReport && Boolean(jobName),
    queryFn: async (): Promise<ValidationReport> => {
      const blob = await ironSwarmDownloadJobResult(workspace, jobName ?? '', VALIDATION_RESULT);
      return JSON.parse(await blob.text()) as ValidationReport;
    },
  });

  return { report: query.data, isLoading: Boolean(jobName) && !hasReport, hasReport };
};

// Recover the composed workflow a sanity check validated (its `composed-workflow` result), so "Apply to Agent"
// stays enabled after a reload when the in-memory copy is gone.
export const useSanityCheckComposedWorkflow = (
  workspace: string,
  jobName: string | undefined
): string | undefined => {
  const { data: results } = useIronSwarmListJobResults(workspace, jobName ?? '', {
    query: {
      enabled: Boolean(jobName),
      refetchInterval: (query) =>
        query.state.data?.data?.some((result) => result.name === COMPOSED_WORKFLOW_RESULT)
          ? false
          : JOB_POLLING_INTERVAL_MS,
    },
  });
  const hasComposed = Boolean(
    results?.data?.some((result) => result.name === COMPOSED_WORKFLOW_RESULT)
  );
  const query = useQuery({
    queryKey: ['iron-swarm-composed-workflow', workspace, jobName],
    enabled: hasComposed && Boolean(jobName),
    queryFn: async (): Promise<string> => {
      const blob = await ironSwarmDownloadJobResult(
        workspace,
        jobName ?? '',
        COMPOSED_WORKFLOW_RESULT
      );
      return blob.text();
    },
  });
  return query.data ?? undefined;
};

// The run entity carries `source_run` (set on validate-only sanity checks); the generated type predates it.
type RunWithSource = IronSwarmRun & { source_run?: string; job_id?: string; name?: string };

// Find the job of the most recent sanity check launched from `runName`, so the Harden tab can re-attach the
// scorecard after a reload / re-visit (the in-memory job name doesn't survive a full page load). Sanity runs
// are the only runs with `source_run` set, so matching it uniquely identifies this run's checks.
export const useLatestSanityCheckJob = (workspace: string, runName: string): string | undefined => {
  const { data } = useQuery({
    queryKey: ['iron-swarm-sanity-lookup', workspace, runName],
    enabled: Boolean(runName),
    refetchInterval: JOB_POLLING_INTERVAL_MS,
    queryFn: async (): Promise<string | undefined> => {
      const res = await ironSwarmListRuns(workspace, { sort: '-created_at', page_size: 50 });
      const runs = (res.data ?? []) as RunWithSource[];
      // Newest-first, so the first match is the latest sanity check for this run.
      return runs.find((r) => r.source_run === runName)?.job_id;
    },
  });
  return data ?? undefined;
};
