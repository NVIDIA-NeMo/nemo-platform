// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CJobTerminalStatuses } from '@nemo/common/src/constants/query';
import { useLiveSeconds } from '@nemo/common/src/hooks/useLiveSeconds';
import { Stack } from '@nvidia/foundations-react-core';
import { RunConfigurationPanel } from '@studio/components/CustomizationOverview/RunConfigurationPanel';
import { TrainingLossPanel } from '@studio/components/CustomizationOverview/TrainingLossPanel';
import { ErrorMessageWithRetry } from '@studio/components/ErrorMessageWithRetry';
import { Loading } from '@studio/components/Layouts/Loading';
import { CustomizationConfigSidePanel } from '@studio/components/sidePanels/CustomizationConfigSidePanel';
import { useCustomizationFilesAsRows } from '@studio/hooks/useCustomizationFiles';
import { useCustomizationJob } from '@studio/hooks/useCustomizationJob';
import { useCustomizationJobStatus } from '@studio/hooks/useCustomizationJobStatus';
import { hasMetrics } from '@studio/types/customization';
import {
  getCustomizationTrainingSteps,
  getDatasetUri,
  getJobDuration,
  getJobStartDate,
  getLossTiles,
  getTrainingProgressTiles,
  getTrainingBatchSize,
  getTrainingDiagnosticsTiles,
  getTrainingTelemetry,
} from '@studio/util/customizations';
import { type FC, useState } from 'react';

type Props = {
  customizationJobName: string;
  workspace?: string;
};

export const CustomizationOverview: FC<Props> = ({ customizationJobName, workspace = '' }) => {
  const [openConfigSidePanel, setOpenConfigSidePanel] = useState(false);
  const {
    job: customization,
    isLoading: isLoadingCustomization,
    isError,
    refetch,
    backend,
  } = useCustomizationJob(workspace, customizationJobName);

  const { steps } = useCustomizationJobStatus(
    workspace,
    customizationJobName,
    backend,
    customization?.status
  );

  const isTerminalStatus = Boolean(
    customization?.status && CJobTerminalStatuses.includes(customization.status)
  );

  const statusDetails = customization?.status_details;
  const telemetry = getTrainingTelemetry(customization);

  const liveSeconds = useLiveSeconds({
    startDate: isTerminalStatus ? undefined : getJobStartDate(steps),
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

  if (isLoading) {
    return <Loading />;
  }

  if (isError) {
    return <ErrorMessageWithRetry onRetry={refetch} />;
  }

  if (!customization) {
    return null;
  }

  const diagnosticsTiles = getTrainingDiagnosticsTiles(
    telemetry,
    hasMetrics(statusDetails) ? statusDetails : undefined,
    {
      isTerminal: isTerminalStatus,
      duration: getJobDuration(steps, isTerminalStatus, liveSeconds),
    }
  );

  const lossTiles = getLossTiles(
    hasMetrics(statusDetails) ? statusDetails : undefined,
    isTerminalStatus
  );

  return (
    <Stack gap="density-xl">
      <TrainingLossPanel
        trainLoss={hasMetrics(statusDetails) ? statusDetails.metrics?.train_loss : undefined}
        valLoss={hasMetrics(statusDetails) ? statusDetails.metrics?.val_loss : undefined}
        maxSteps={maxXAxisValue}
        metrics={[...lossTiles, ...diagnosticsTiles]}
        progress={getTrainingProgressTiles(telemetry)}
      />

      <RunConfigurationPanel
        customization={customization}
        telemetry={telemetry}
        onViewConfiguration={() => setOpenConfigSidePanel(true)}
      />

      <CustomizationConfigSidePanel
        open={openConfigSidePanel}
        onOpenChange={setOpenConfigSidePanel}
        customizationJobName={customizationJobName}
        workspace={workspace}
      />
    </Stack>
  );
};
