// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ironSwarmDownloadJobResult, useIronSwarmListJobResults } from '@iron-swarm/generated/api';
import type { PlatformJobStatus } from '@iron-swarm/generated/schema';
import { CJobTerminalStatuses, JOB_POLLING_INTERVAL_MS } from '@nemo/common';
import { useQuery } from '@tanstack/react-query';

export interface JobArtifact<T> {
  /** Parsed artifact, once it has been downloaded. */
  data: T | undefined;
  /** The artifact exists in the job's result list. */
  present: boolean;
  /** Still waiting on the artifact, and the job could still produce it. */
  isLoading: boolean;
  /**
   * The job reached a terminal status without ever writing the artifact — it failed, was
   * cancelled, or completed without producing one. Callers should render an error here;
   * otherwise a failed job leaves the UI on a spinner forever.
   */
  missing: boolean;
}

/**
 * Poll a job's result list until `resultName` appears, then download and parse it once.
 *
 * Artifact presence alone is not a safe stop condition: a job that errors or is cancelled never
 * writes its result, so polling on that alone runs every {@link JOB_POLLING_INTERVAL_MS} for as
 * long as the page is mounted and the caller stays stuck loading. Passing `status` lets the poll
 * stop on a terminal job and surface {@link JobArtifact.missing} instead.
 */
export const useJobArtifact = <T>(
  workspace: string,
  jobName: string | undefined,
  resultName: string,
  parse: (blob: Blob) => Promise<T>,
  status?: PlatformJobStatus
): JobArtifact<T> => {
  const terminal = Boolean(status && CJobTerminalStatuses.includes(status));

  const { data: results } = useIronSwarmListJobResults(workspace, jobName ?? '', {
    query: {
      enabled: Boolean(jobName),
      refetchInterval: (query) => {
        const found = query.state.data?.data?.some((result) => result.name === resultName);
        // A terminal job will not produce anything further, so stop either way.
        return found || terminal ? false : JOB_POLLING_INTERVAL_MS;
      },
    },
  });

  const present = Boolean(results?.data?.some((result) => result.name === resultName));

  const query = useQuery({
    queryKey: ['iron-swarm-job-artifact', workspace, jobName, resultName],
    enabled: present && Boolean(jobName),
    queryFn: () => ironSwarmDownloadJobResult(workspace, jobName ?? '', resultName).then(parse),
  });

  return {
    data: query.data,
    present,
    isLoading: Boolean(jobName) && !present && !terminal,
    missing: Boolean(jobName) && terminal && !present,
  };
};

export const parseJson = <T>(blob: Blob): Promise<T> =>
  blob.text().then((text) => JSON.parse(text) as T);

export const parseText = (blob: Blob): Promise<string> => blob.text();
