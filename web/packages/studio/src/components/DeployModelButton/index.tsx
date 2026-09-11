// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { LoadingButton } from '@nemo/common/src/components/LoadingButton';
import { getURNFromNamedEntityRef } from '@nemo/common/src/namedEntity';
import type { ModelEntity } from '@nemo/sdk/generated/platform/schema';
import { DEPLOYMENTS_ENABLED } from '@studio/constants/environment';
import { canFineTuneModel } from '@studio/hooks/useModelCustomizationEligibility';
import { useModelDeploymentStatus } from '@studio/hooks/useModelDeploymentStatus';
import {
  getWorkspaceDeploymentDetailsRoute,
  getWorkspaceDeploymentsRoute,
} from '@studio/routes/utils';
import type { FC } from 'react';
import { useNavigate } from 'react-router';

export interface DeployModelButtonProps {
  workspace: string;
  model?: ModelEntity;
}

/**
 * Deploy a model, or jump to the deployment already serving it.
 *
 * Renders nothing unless the model can actually be deployed. Deploying from
 * Studio goes through the create-deployment wizard's Workspace source, which
 * only lists models that have a fileset (see `WorkspaceSourceFields`), so
 * offering the action for a fileset-less model would be a dead link. That is
 * the same `canFineTuneModel` predicate the fine-tune picker filters on — every
 * model you can fine-tune is a model you can deploy.
 */
export const DeployModelButton: FC<DeployModelButtonProps> = ({ workspace, model }) => {
  const navigate = useNavigate();
  const { deploymentRef, isLoading } = useModelDeploymentStatus(model);

  if (!DEPLOYMENTS_ENABLED || !model || !canFineTuneModel(model)) return null;

  // A deployment already serves this model — point at it instead of offering to
  // create a second one.
  if (deploymentRef) {
    return (
      <LoadingButton
        kind="secondary"
        size="small"
        className="flex-1"
        height={28}
        loading={isLoading}
        onClick={() =>
          navigate(getWorkspaceDeploymentDetailsRoute(deploymentRef.workspace, deploymentRef.name))
        }
      >
        View Deployment
      </LoadingButton>
    );
  }

  return (
    <LoadingButton
      kind="secondary"
      size="small"
      className="flex-1"
      height={28}
      loading={isLoading}
      onClick={() =>
        navigate(
          getWorkspaceDeploymentsRoute(workspace, { model: getURNFromNamedEntityRef(model) })
        )
      }
    >
      Deploy
    </LoadingButton>
  );
};
