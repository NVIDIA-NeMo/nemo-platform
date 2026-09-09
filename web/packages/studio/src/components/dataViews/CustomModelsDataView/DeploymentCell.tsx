// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useModelsGetModel } from '@nemo/sdk/generated/platform/models';
import { ModelDeploymentStatus } from '@nemo/sdk/generated/platform/schema';
import {
  Anchor,
  Flex,
  Skeleton,
  StatusIndicator,
  Text,
  Tooltip,
} from '@nvidia/foundations-react-core';
import { useModelDeploymentStatus } from '@studio/hooks/useModelDeploymentStatus';
import { getWorkspaceDeploymentDetailsRoute } from '@studio/routes/utils';
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

interface DeploymentCellProps {
  workspace: string;
  providerIds?: string[];
  baseModel: string;
}

/**
 * Where a custom model is served: a status dot plus a link to the deployment.
 *
 * A custom model has no deployment of its own — inference resolves through its
 * base model — so this walks the same path the chat availability check does:
 * fetch the base entity, graft this model's own providers onto it, then resolve
 * provider -> deployment.
 *
 * Rendered for adapter subrows too. An adapter is served by the deployment that
 * loaded its base model, which is the same deployment as its parent row's, and
 * the subrow carries the parent's `model_providers` verbatim. The queries
 * therefore share their parent's cache keys and cost no extra requests.
 */
export const DeploymentCell: FC<DeploymentCellProps> = ({ workspace, providerIds, baseModel }) => {
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

  const {
    status,
    deploymentRef,
    isLoading: isStatusLoading,
  } = useModelDeploymentStatus(resolvedModel);

  if (isLoadingBaseModel || isStatusLoading) {
    return <Skeleton animated aria-label="Loading deployment" className="h-4 w-24 rounded" />;
  }

  if (!deploymentRef) {
    return (
      <Flex gap="density-sm" align="center" className="min-w-0">
        <StatusIndicator color={null} size="small" className="flex-shrink-0" />
        <Text className="truncate text-subtle">Not deployed</Text>
      </Flex>
    );
  }

  // `useModelDeploymentStatus` resolves only the first provider, so a model
  // served by several deployments names one and counts the rest rather than
  // implying the first is the only one.
  const extraProviderCount = Math.max(0, (providerIds?.length ?? 0) - 1);

  return (
    <Flex gap="density-sm" align="center" className="min-w-0">
      <Tooltip slotContent={status ?? 'No deployment found'} className="flex-shrink-0">
        <StatusIndicator
          color={status ? getStatusColor(status) : null}
          size="small"
          className="flex-shrink-0"
        />
      </Tooltip>
      <Anchor
        href={getWorkspaceDeploymentDetailsRoute(deploymentRef.workspace, deploymentRef.name)}
        target="_self"
        className="truncate"
        onClick={(event) => event.stopPropagation()}
      >
        {deploymentRef.name}
      </Anchor>
      {extraProviderCount > 0 && (
        <Tooltip
          slotContent={`Served by ${extraProviderCount + 1} deployments`}
          className="flex-shrink-0"
        >
          <Text className="flex-shrink-0 text-subtle">{`+${extraProviderCount}`}</Text>
        </Tooltip>
      )}
    </Flex>
  );
};
