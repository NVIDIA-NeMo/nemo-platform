// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { CJobCancellableStatuses, CJobLaunchableStatuses } from '@nemo/common/src/constants/query';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { getJobsGetJobQueryKey } from '@nemo/sdk/generated/platform/api';
import { PlatformJobStatus, type PlatformJobResponse } from '@nemo/sdk/generated/platform/schema';
import { useCustomizationCancelJob } from '@nemo/sdk/vendored/customizer/api';
import type { CustomizationBackend } from '@nemo/sdk/vendored/customizer/schema';
import { Button } from '@nvidia/foundations-react-core';
import { getErrorMessage } from '@studio/api/common/utils';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getNewEvaluationMetricRoute } from '@studio/routes/utils';
import { useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { FC } from 'react';
import { useNavigate } from 'react-router-dom';

interface DetailActionsProps {
  model?: string;
  status?: PlatformJobStatus;
  /** Training backend of this job, needed to target the correct per-backend cancel endpoint. */
  backend?: CustomizationBackend;
  /** Job name (from the route). */
  name: string;
}

/**
 * This component renders the primary top-level CTAs for the customization job details page.
 */
export const DetailActions: FC<DetailActionsProps> = ({ model, status, backend, name }) => {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const workspace = useWorkspaceFromPath();
  const { mutateAsync, isPending } = useCustomizationCancelJob({
    mutation: {
      onSuccess: () => {
        toast.success('Job cancelled successfully.');
        // Optimistically update the cached (generic) job status to cancelled
        queryClient.setQueryData(
          getJobsGetJobQueryKey(workspace, name),
          (oldData: PlatformJobResponse | undefined) => {
            if (!oldData) return oldData;
            return {
              ...oldData,
              status: PlatformJobStatus.cancelled,
            };
          }
        );
      },
    },
  });

  const cancelJob = async () => {
    if (!backend) {
      toast.error('Unable to determine the training backend for this job.');
      return;
    }
    try {
      await mutateAsync({ workspace, backend, name });
    } catch (e) {
      if (e instanceof AxiosError || e instanceof Error) {
        toast.error(`Failed to cancel job: ${getErrorMessage(e)}`);
      } else {
        toast.error('Failed to cancel job: Unknown error');
      }
    }
  };

  const disabled = isPending || !backend;
  if (isPending || status === PlatformJobStatus.cancelling) {
    return (
      <LoadingButton kind="secondary" loading disabled>
        Cancelling...
      </LoadingButton>
    );
  } else if (status && CJobCancellableStatuses.includes(status)) {
    return (
      <Button kind="secondary" onClick={cancelJob} disabled={disabled}>
        Cancel Job
      </Button>
    );
  } else if (status && CJobLaunchableStatuses.includes(status)) {
    return (
      <Button
        color="brand"
        disabled={disabled}
        onClick={() => {
          navigate(getNewEvaluationMetricRoute(workspace, { model }));
        }}
      >
        Evaluate
      </Button>
    );
  }
};
