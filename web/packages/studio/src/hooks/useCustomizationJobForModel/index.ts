// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useJobsListJobs } from '@nemo/sdk/generated/platform/jobs';
import type {
  ModelEntity,
  PlatformJobListSortField,
  PlatformJobResponse,
  PlatformJobsListFilter,
} from '@nemo/sdk/generated/platform/schema';
import { JOB_SOURCE } from '@studio/components/dataViews/JobsDataView/constants';

const MAX_CUSTOMIZATION_JOBS_SCANNED = 100;

export interface UseCustomizationJobForModelResult {
  jobName: string | undefined;
  isLoading: boolean;
}

const jobOutputName = (job: PlatformJobResponse): string | undefined => {
  const output = (job.spec as { output?: { name?: unknown } } | undefined)?.output;
  return typeof output?.name === 'string' ? output.name : undefined;
};

/**
 * Resolves the customization job that produced a fine-tuned checkpoint, for linking
 * a model back to its originating job. A ModelEntity has no job reference, so match
 * `spec.output.name` (set by every customizer backend) client-side — the jobs `spec`
 * filter is missing on older deployed services, while `source` filtering is not.
 */
export const useCustomizationJobForModel = (
  workspace: string,
  model: ModelEntity | null | undefined
): UseCustomizationJobForModelResult => {
  const modelName = model?.name;
  const enabled = Boolean(modelName);

  const { data, isLoading } = useJobsListJobs(
    workspace,
    {
      page: 1,
      page_size: MAX_CUSTOMIZATION_JOBS_SCANNED,
      sort: '-created_at' as PlatformJobListSortField,
      filter: { source: JOB_SOURCE.CUSTOMIZATION } as unknown as PlatformJobsListFilter,
    },
    { query: { enabled } }
  );

  const jobName = data?.data?.find((job) => jobOutputName(job) === modelName)?.name;

  return { jobName, isLoading: enabled && isLoading };
};
