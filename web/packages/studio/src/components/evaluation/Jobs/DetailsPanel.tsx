// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { DownloadEvaluationLogsButton } from '@nemo/common/src/components/buttons/DownloadEvaluationLogsButton';
import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { KVPair } from '@nemo/common/src/components/KVPair';
import { PanelFooterAccordion } from '@nemo/common/src/components/PanelFooterAccordion';
import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { PlatformJobTerminalStatuses } from '@nemo/common/src/constants/query';
import { useLiveSeconds } from '@nemo/common/src/hooks/useLiveSeconds';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import {
  formatTimeInSeconds,
  getDifferenceInMilliseconds,
  utcToLocalDate,
} from '@nemo/common/src/utils/date';
import {
  getEvaluatorGetEvaluateJobQueryKey,
  useEvaluatorCancelEvaluateJob,
} from '@nemo/sdk/generated/evaluator/api';
import type { EvaluateJob } from '@nemo/sdk/generated/evaluator/schema';
import { Banner, Button, Flex, Modal, Panel, Stack, Text } from '@nvidia/foundations-react-core';
import { ButtonLaunchEvaluation } from '@studio/components/evaluation/ButtonLaunchEvaluation';
import { StatusLogsContent } from '@studio/components/evaluation/Jobs/StatusLogsContent';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useQueryClient } from '@tanstack/react-query';
import { ChartBar, LayoutList, CircleX } from 'lucide-react';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

interface DetailsPanelProps {
  evaluationJob?: EvaluateJob;
  error?: boolean;
}

export const DetailsPanel = ({ evaluationJob, error }: DetailsPanelProps) => {
  const navigate = useNavigate();
  const workspace = useWorkspaceFromPath();
  const toast = useToast();
  const queryClient = useQueryClient();
  const [cancelModalOpen, setCancelModalOpen] = useState(false);
  const { mutateAsync: cancelJob, isPending: isCancelling } = useEvaluatorCancelEvaluateJob();

  const handleRefreshClick = () => {
    navigate(0);
  };

  const handleCancelJob = async () => {
    if (!evaluationJob?.name) return;

    try {
      await cancelJob({ workspace, name: evaluationJob.name });
      toast.success('Job cancellation requested');

      await queryClient.invalidateQueries({
        queryKey: getEvaluatorGetEvaluateJobQueryKey(workspace, evaluationJob.name),
      });

      setCancelModalOpen(false);
    } catch (error) {
      console.error('Failed to cancel job:', error);
      toast.error('Failed to cancel job. Please try again.');
    }
  };

  const differenceInMilliseconds = getDifferenceInMilliseconds(
    evaluationJob?.created_at,
    evaluationJob?.updated_at
  );
  const elapsedSeconds = differenceInMilliseconds
    ? Math.floor(differenceInMilliseconds / 1000)
    : undefined;
  const isTerminalStatus =
    evaluationJob?.status && PlatformJobTerminalStatuses.includes(evaluationJob.status);
  const canCancelJob = evaluationJob?.status && !isTerminalStatus;
  const liveSeconds = useLiveSeconds({
    startDate: !isTerminalStatus ? utcToLocalDate(evaluationJob?.created_at) : undefined,
  });

  if (error || !evaluationJob) {
    return (
      <ErrorMessage
        header="Failed to Load Job"
        message="Unable to load job. Please try again."
        slotFooter={
          <>
            <Button color="neutral" kind="tertiary" onClick={handleRefreshClick}>
              Reload Job
            </Button>
            <ButtonLaunchEvaluation />
          </>
        }
      />
    );
  }

  const {
    status,
    created_at,
    id: evalJobId,
    name: jobName,
    description,
    error_details,
  } = evaluationJob;
  const status_details = evaluationJob.status_details as
    | { message?: string; stage?: string; progress?: number }
    | undefined;

  const model = evaluationJob.spec.target?.name;

  return (
    <>
      <Panel
        elevation="high"
        slotHeading={
          <Flex align="center" justify="between" className="w-full">
            <Flex align="center" gap="2">
              <ChartBar />
              Details
            </Flex>
            {canCancelJob && (
              <Button
                kind="tertiary"
                color="danger"
                size="small"
                onClick={() => setCancelModalOpen(true)}
              >
                <CircleX /> Cancel Job
              </Button>
            )}
          </Flex>
        }
        attributes={{
          PanelFooter: {
            className:
              'overflow-hidden -ml-density-2xl -mr-density-2xl -mb-density-2xl rounded-b-density-xl',
          },
        }}
        slotFooter={
          <PanelFooterAccordion
            slotTrigger={
              <Flex align="center" gap="2">
                <LayoutList />
                Status Logs
              </Flex>
            }
            slotContent={
              jobName ? <StatusLogsContent workspace={workspace} jobName={jobName} /> : null
            }
            value="status-logs"
          />
        }
      >
        <Stack gap="4">
          {status === 'error' && (
            <Banner
              kind="inline"
              status="error"
              slotActions={
                <DownloadEvaluationLogsButton
                  workspace={workspace}
                  jobName={jobName ?? ''}
                  size="small"
                  kind="secondary"
                />
              }
            >
              {typeof error_details?.message === 'string'
                ? error_details.message
                : error_details?.message != null
                  ? String(error_details.message)
                  : 'Task has failed due to an error.'}
            </Banner>
          )}
          <KVPair label="Job Name" value={jobName || 'Detail not available'} />
          {description && <KVPair label="Description" value={description} />}
          <KVPair
            label="Status"
            value={
              status ? (
                <Flex align="center" gap="2">
                  <StatusBadge status={status} />
                  {formatTimeInSeconds(
                    PlatformJobTerminalStatuses.includes(status) ? elapsedSeconds : liveSeconds
                  )}
                </Flex>
              ) : (
                <Text kind="body/semibold/sm">Detail not available</Text>
              )
            }
          />
          {status_details?.message && (
            <KVPair
              label="Status Details"
              value={
                <Stack gap="1">
                  {status_details.stage && (
                    <Text kind="body/regular/sm">Stage: {String(status_details.stage)}</Text>
                  )}
                  {status_details.progress !== undefined && (
                    <Text kind="body/regular/sm">
                      Progress: {String(status_details.progress.toFixed(2))}%
                    </Text>
                  )}
                  <Text kind="body/regular/sm">{String(status_details.message)}</Text>
                </Stack>
              }
            />
          )}
          <KVPair label="Job ID" value={evalJobId || 'Detail not available'} />
          <KVPair
            label="Model"
            value={
              model ? (
                <Text kind="body/semibold/sm">{model}</Text>
              ) : (
                <Text kind="body/semibold/sm">Detail not available</Text>
              )
            }
          />
          <KVPair
            label="Created"
            value={created_at ? formatAbsoluteTimestamp(created_at) : 'Detail not available'}
          />
        </Stack>
      </Panel>

      {/* Cancel Job Confirmation Modal */}
      <Modal
        open={cancelModalOpen}
        onOpenChange={(open) => !isCancelling && setCancelModalOpen(open)}
        slotHeading={
          <Flex align="center" gap="density-sm">
            <CircleX />
            Cancel Evaluation Job
          </Flex>
        }
        slotFooter={
          <Flex justify="end" gap="density-xs" align="center" className="w-full">
            <Button
              onClick={() => setCancelModalOpen(false)}
              kind="tertiary"
              color="neutral"
              disabled={isCancelling}
            >
              Go Back
            </Button>
            <Button color="danger" onClick={handleCancelJob} disabled={isCancelling}>
              {isCancelling ? 'Cancelling...' : 'Cancel Job'}
            </Button>
          </Flex>
        }
      >
        <Stack gap="density-md">
          <Text>
            Are you sure you want to cancel job <strong>{jobName}</strong>?
          </Text>
          <Text>The job will stop processing and cannot be resumed.</Text>
        </Stack>
      </Modal>
    </>
  );
};
