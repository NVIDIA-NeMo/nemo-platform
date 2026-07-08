// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { KVPair } from '@nemo/common/src/components/KVPair';
import { PanelFooterAccordion } from '@nemo/common/src/components/PanelFooterAccordion';
import { formatAbsoluteTimestamp } from '@nemo/common/src/components/RelativeTime/util';
import { StatusBadge } from '@nemo/common/src/components/StatusBadge';
import { CJobTerminalStatuses } from '@nemo/common/src/constants/query';
import { useJobLogs } from '@nemo/common/src/hooks/useJobLogs';
import { useLiveSeconds } from '@nemo/common/src/hooks/useLiveSeconds';
import { useToast } from '@nemo/common/src/providers/toast/useToast';
import { formatTimeInSeconds, utcToLocalDate } from '@nemo/common/src/utils/date';
import { formatLogs } from '@nemo/common/src/utils/logs';
import { getJobRefetchInterval } from '@nemo/common/src/utils/query';
import {
  Button,
  CodeSnippet,
  Flex,
  Grid,
  Panel,
  Stack,
  Text,
} from '@nvidia/foundations-react-core';
import { TrainValidationLossLineChart } from '@studio/components/charts/TrainValidationLossLineChart';
import { ErrorMessageWithRetry } from '@studio/components/ErrorMessageWithRetry';
import { Loading } from '@studio/components/Layouts/Loading';
import { CustomizationConfigSidePanel } from '@studio/components/sidePanels/CustomizationConfigSidePanel';
import { useCustomizationFilesAsRows } from '@studio/hooks/useCustomizationFiles';
import { useCustomizationJob } from '@studio/hooks/useCustomizationJob';
import { hasMetrics } from '@studio/types/customization';
import {
  getBaseModel,
  getCustomizationTrainingProgress,
  getCustomizationTrainingSteps,
  getDatasetUri,
  getTrainingBatchSize,
} from '@studio/util/customizations';
import { formatElapsedTime } from '@studio/util/date';
import { Cog, LayoutList, Play } from 'lucide-react';
import { FC, useState } from 'react';

type Props = {
  customizationJobName: string;
  workspace?: string;
};
export const CustomizationDetailsPanel: FC<Props> = ({ customizationJobName, workspace = '' }) => {
  const toast = useToast();
  const [openConfigSidePanel, setOpenConfigSidePanel] = useState(false);
  const {
    job: customization,
    isLoading: isLoadingCustomization,
    isError,
    refetch,
  } = useCustomizationJob(workspace, customizationJobName, {
    refetchInterval: (query) => getJobRefetchInterval(query.state.data?.status),
  });

  const { data: logs } = useJobLogs({
    workspace,
    name: customizationJobName,
    enabled: !!customization,
    jobStatus: customization?.status,
  });

  const isTerminalStatus =
    customization?.status && CJobTerminalStatuses.includes(customization.status);

  const statusDetails = customization?.status_details;

  const liveSeconds = useLiveSeconds({
    startDate:
      !isTerminalStatus && customization?.created_at
        ? utcToLocalDate(customization.created_at)
        : undefined,
  });

  const {
    trainingRecords,
    validationRecords,
    isPending: isFilesLoading,
  } = useCustomizationFilesAsRows({
    fileset: getDatasetUri(customization) || undefined,
  });

  const epochs = customization?.spec?.schedule?.epochs;
  const batchSize = getTrainingBatchSize(customization);
  const maxXAxisValue = getCustomizationTrainingSteps({
    epochs: epochs ?? 0,
    batchSize,
    trainingRecords,
    hasValidationDataset: validationRecords > 0,
  });
  const isLoading = isLoadingCustomization || isFilesLoading;

  let content;
  if (isLoading) {
    content = <Loading />;
  } else if (isError) {
    content = <ErrorMessageWithRetry onRetry={refetch} />;
  } else if (customization) {
    content = (
      <Grid cols={{ md: 1, lg: 2 }} gap="density-xl">
        <Stack className="flex-1" gap="density-xl">
          <KVPair
            label="Status"
            value={
              customization.status ? (
                <Flex align="center" gap="2">
                  <StatusBadge status={customization.status} />
                  {CJobTerminalStatuses.includes(customization.status) &&
                  customization.created_at &&
                  customization.updated_at
                    ? formatElapsedTime(
                        new Date(customization.created_at),
                        new Date(customization.updated_at)
                      )
                    : formatTimeInSeconds(liveSeconds)}
                </Flex>
              ) : (
                <Text kind="body/semibold/sm">Detail not available</Text>
              )
            }
          />
          <KVPair
            label="Epochs Completed"
            value={getCustomizationTrainingProgress(customization)}
          />
          <KVPair label="Customization ID" value={customization.id} />
          <KVPair label="Output Model" value={customization.spec?.output?.name ?? '-'} />
          <KVPair label="Configuration" value={getBaseModel(customization) || '-'} />
          <KVPair label="Description" value={customization.description || '-'} />
          <KVPair
            label="Created"
            value={
              customization.created_at ? formatAbsoluteTimestamp(customization.created_at) : '-'
            }
          />
          <KVPair
            label="Owner"
            value={
              customization.ownership?.created_by ? String(customization.ownership.created_by) : '-'
            }
          />
          <Button
            kind="tertiary"
            size="small"
            onClick={() => setOpenConfigSidePanel(true)}
            className="-ml-density-md"
          >
            <Cog />
            View Job Configuration
          </Button>
        </Stack>
        <TrainValidationLossLineChart
          trainLoss={hasMetrics(statusDetails) ? statusDetails.metrics?.train_loss : undefined}
          valLoss={hasMetrics(statusDetails) ? statusDetails.metrics?.val_loss : undefined}
          attributes={{
            XAxis: {
              domain: ['dataMin', maxXAxisValue],
            },
          }}
        />
      </Grid>
    );
  }

  // Fallback to status details if logs are not available
  const codeSnippet = logs?.length
    ? formatLogs(logs)
    : (JSON.stringify(customization?.status_details?.events, null, 2) ?? '');

  return (
    <Panel
      elevation="high"
      attributes={{
        PanelFooter: {
          className:
            'overflow-hidden -ml-density-2xl -mr-density-2xl -mb-density-2xl rounded-b-density-xl',
        },
      }}
      slotHeading="Training Progress"
      slotIcon={<Play />}
      slotFooter={
        <PanelFooterAccordion
          value="status-logs"
          slotTrigger={
            <Flex align="center" gap="2">
              <LayoutList />
              Status Logs
            </Flex>
          }
          slotContent={
            <Flex className="h-full">
              <CodeSnippet
                className="h-full w-full"
                value={codeSnippet}
                language="shell"
                kind="block"
                onCopySuccess={() => toast.success('Logs copied to clipboard')}
              />
            </Flex>
          }
        />
      }
    >
      {content}
      <CustomizationConfigSidePanel
        open={openConfigSidePanel}
        onOpenChange={setOpenConfigSidePanel}
        customizationJobName={customizationJobName}
        workspace={workspace}
      />
    </Panel>
  );
};
