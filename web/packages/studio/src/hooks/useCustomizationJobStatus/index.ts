// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getJobRefetchInterval } from '@nemo/common/src/utils/query';
import {
  customizationGetAutomodelJobStatus,
  customizationGetRlJobStatus,
  customizationGetUnslothJobStatus,
  getCustomizationGetAutomodelJobStatusQueryKey,
  getCustomizationGetRlJobStatusQueryKey,
  getCustomizationGetUnslothJobStatusQueryKey,
} from '@nemo/sdk/generated/customizer/api';
import type {
  PlatformJobStatusResponse,
  PlatformJobStepStatusResponse,
} from '@nemo/sdk/generated/customizer/schema';
import type { PlatformJobStatus } from '@nemo/sdk/generated/platform/schema';
import type { CustomizationBackend } from '@studio/util/customizationBackend';
import { skipToken, useQuery } from '@tanstack/react-query';

interface StatusEndpoint {
  fetchStatus: (
    workspace: string,
    name: string,
    signal?: AbortSignal
  ) => Promise<PlatformJobStatusResponse>;
  getQueryKey: (workspace: string, name: string) => readonly string[];
}

const STATUS_ENDPOINTS: Record<CustomizationBackend, StatusEndpoint> = {
  automodel: {
    fetchStatus: customizationGetAutomodelJobStatus,
    getQueryKey: getCustomizationGetAutomodelJobStatusQueryKey,
  },
  unsloth: {
    fetchStatus: customizationGetUnslothJobStatus,
    getQueryKey: getCustomizationGetUnslothJobStatusQueryKey,
  },
  rl: {
    fetchStatus: customizationGetRlJobStatus,
    getQueryKey: getCustomizationGetRlJobStatusQueryKey,
  },
};

/** Key used while the backend is still unknown, so the query has a stable identity. */
const PENDING_BACKEND_QUERY_KEY = ['customization-job-status', 'pending-backend'] as const;

export const getCustomizationJobStatusQueryKey = (
  backend: CustomizationBackend,
  workspace: string,
  name: string
): readonly string[] => STATUS_ENDPOINTS[backend].getQueryKey(workspace, name);

export interface UseCustomizationJobStatusResult {
  steps: PlatformJobStepStatusResponse[];
  isLoading: boolean;
  isError: boolean;
}

interface UseCustomizationJobStatusOptions {
  /**
   * Defaults to true. TanStack schedules `refetchInterval` per observer, so a second consumer of
   * this hook doubles the request rate against `/status` rather than sharing the first one's
   * polling — callers that only need the steps in some states should opt out of the rest.
   */
  enabled?: boolean;
}

export const useCustomizationJobStatus = (
  workspace: string,
  name: string,
  backend: CustomizationBackend | undefined,
  jobStatus?: PlatformJobStatus,
  { enabled = true }: UseCustomizationJobStatusOptions = {}
): UseCustomizationJobStatusResult => {
  const endpoint = backend ? STATUS_ENDPOINTS[backend] : undefined;
  const canFetch = Boolean(endpoint && workspace && name && enabled);

  const { data, isLoading, isError } = useQuery({
    queryKey: endpoint ? endpoint.getQueryKey(workspace, name) : PENDING_BACKEND_QUERY_KEY,
    queryFn:
      endpoint && canFetch
        ? ({ signal }) => endpoint.fetchStatus(workspace, name, signal)
        : skipToken,
    refetchInterval: getJobRefetchInterval(jobStatus),
  });

  return {
    steps: data?.steps ?? [],
    isLoading,
    isError,
  };
};
