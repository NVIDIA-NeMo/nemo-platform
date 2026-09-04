// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useModelsGetModel } from '@nemo/sdk/generated/platform/models';
import { ModelDeploymentStatus } from '@nemo/sdk/generated/platform/schema';
import { Skeleton, StatusIndicator, Tooltip } from '@nvidia/foundations-react-core';
import { useModelDeploymentStatus } from '@studio/hooks/useModelDeploymentStatus';
import type { FC } from 'react';

const getStatusColor = (status: ModelDeploymentStatus) => {
  switch (status) {
    case ModelDeploymentStatus.READY:
      return 'green' as const;
    case ModelDeploymentStatus.PENDING:
    case ModelDeploymentStatus.CREATED:
    case ModelDeploymentStatus.DELETING:
      return 'yellow' as const;
    case ModelDeploymentStatus.ERROR:
    case ModelDeploymentStatus.DELETED:
    case ModelDeploymentStatus.LOST:
      return 'red' as const;
    case ModelDeploymentStatus.UNKNOWN:
    default:
      return null;
  }
};

interface DeploymentIndicatorProps {
  workspace: string;
  providerIds?: string[];
  baseModel: string;
}

export const DeploymentIndicator: FC<DeploymentIndicatorProps> = ({
  workspace,
  providerIds,
  baseModel,
}) => {
  const { data: baseModelEntity, isLoading: isLoadingBaseModel } = useModelsGetModel(
    workspace,
    baseModel,
    undefined,
    { query: { enabled: Boolean(baseModel), retry: false } }
  );

  const resolvedModel =
    providerIds?.length && baseModelEntity
      ? { ...baseModelEntity, model_providers: providerIds }
      : baseModelEntity;

  const { status, isLoading: isStatusLoading } = useModelDeploymentStatus(resolvedModel);

  const isLoading = isLoadingBaseModel || isStatusLoading;

  if (isLoading) return <Skeleton animated className="size-2 rounded-full" />;
  if (!status) {
    return (
      <Tooltip slotContent="No deployment found" className="flex-shrink-0">
        <StatusIndicator color={null} size="small" className="flex-shrink-0" />
      </Tooltip>
    );
  }
  return (
    <Tooltip slotContent={status} className="flex-shrink-0">
      <StatusIndicator color={getStatusColor(status)} size="small" className="flex-shrink-0" />
    </Tooltip>
  );
};
