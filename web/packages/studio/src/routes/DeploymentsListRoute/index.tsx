/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

import { AccessibleTitle } from '@nemo/common/src/components/AccessibleTitle';
import { DeleteConfirmationModal } from '@nemo/common/src/components/DeleteConfirmationModal';
import { resourceRefSchema, type ResourceRef } from '@nemo/common/src/types';
import { ModelDeployment } from '@nemo/sdk/generated/platform/schema';
import { Button, Flex, PageHeader, Stack } from '@nvidia/foundations-react-core';
import { DeploymentsDataView } from '@studio/components/dataViews/DeploymentsDataView';
import { DocumentationButton } from '@studio/components/DocumentationButton';
import { LINK_DOCS_DEPLOYMENTS } from '@studio/constants/links';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import {
  CreateDeploymentSidePanel,
  type CreateDeploymentPrefill,
} from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel';
import { DeploymentDetailsSidePanel } from '@studio/routes/DeploymentsListRoute/DeploymentDetailsSidePanel';
import { useDeleteDeploymentAndConfig } from '@studio/routes/DeploymentsListRoute/useDeleteDeploymentAndConfig';
import {
  DEPLOYMENT_DETAILS_PANEL_VIEW_DETAILS,
  getWorkspaceDeploymentDetailsRoute,
  getWorkspaceDeploymentsRoute,
} from '@studio/routes/utils';
import { FC, useCallback, useEffect, useMemo, useState } from 'react';
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router';

function getResourceRefSearchParam(params: URLSearchParams, name: string): ResourceRef | undefined {
  const value = params.get(name);
  if (!value) return undefined;
  const parsed = resourceRefSchema.safeParse(value);
  return parsed.success ? parsed.data : undefined;
}

export const DeploymentsListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const navigate = useNavigate();
  const { deploymentName: deploymentNameParam, deploymentPanelView } = useParams<{
    deploymentName?: string;
    deploymentPanelView?: string;
  }>();

  // `useParams()` already returns decoded values; route helpers handle encoding.
  const deploymentNameFromPath = deploymentNameParam ?? '';

  const [isCreateDeploymentOpen, setIsCreateDeploymentOpen] = useState(false);
  const [deploymentToDelete, setDeploymentToDelete] = useState<ModelDeployment | null>(null);

  const [searchParams, setSearchParams] = useSearchParams();
  const searchParamString = searchParams.toString();
  const createPrefill = useMemo<CreateDeploymentPrefill | undefined>(() => {
    const params = new URLSearchParams(searchParamString);
    const modelRef = getResourceRefSearchParam(params, 'model');
    if (modelRef) return { modelRef };
    const fileset = getResourceRefSearchParam(params, 'fileset');
    return fileset ? { fileset } : undefined;
  }, [searchParamString]);
  const hasPrefillParams = searchParams.has('model') || searchParams.has('fileset');

  // Deep-link: opening the panel happens automatically when `?model=` or `?fileset=` is in the URL.
  useEffect(() => {
    if (createPrefill) setIsCreateDeploymentOpen(true);
  }, [createPrefill]);

  const detailsPanelOpen =
    Boolean(deploymentNameFromPath) &&
    deploymentPanelView === DEPLOYMENT_DETAILS_PANEL_VIEW_DETAILS;

  const { deleteDeploymentAndConfig } = useDeleteDeploymentAndConfig(workspace);

  const handleCloseDetailsPanel = useCallback(() => {
    navigate(getWorkspaceDeploymentsRoute(workspace), { replace: true });
  }, [navigate, workspace]);

  const handleDeleteDeployment = useCallback(async () => {
    if (!deploymentToDelete) return false;
    try {
      await deleteDeploymentAndConfig(deploymentToDelete);
      if (detailsPanelOpen && deploymentToDelete.name === deploymentNameFromPath) {
        navigate(getWorkspaceDeploymentsRoute(workspace), { replace: true });
      }
      return true;
    } catch {
      return false;
    }
  }, [
    deleteDeploymentAndConfig,
    deploymentNameFromPath,
    deploymentToDelete,
    detailsPanelOpen,
    navigate,
    workspace,
  ]);

  const handleModalClose = useCallback(() => setDeploymentToDelete(null), []);

  useBreadcrumbs({
    items: [
      {
        href: getWorkspaceDeploymentsRoute(workspace),
        slotLabel: 'Deployments',
      },
    ],
  });

  const docsButton = <DocumentationButton href={LINK_DOCS_DEPLOYMENTS} />;
  const createDeploymentButton = (
    <Button color="brand" onClick={() => setIsCreateDeploymentOpen(true)}>
      Create Deployment
    </Button>
  );

  /** Only `details` is supported; normalize unknown segments to avoid broken URLs. */
  if (
    deploymentNameFromPath &&
    deploymentPanelView &&
    deploymentPanelView !== DEPLOYMENT_DETAILS_PANEL_VIEW_DETAILS
  ) {
    return (
      <Navigate
        replace
        to={getWorkspaceDeploymentDetailsRoute(
          workspace,
          deploymentNameFromPath,
          DEPLOYMENT_DETAILS_PANEL_VIEW_DETAILS
        )}
      />
    );
  }

  return (
    <AccessibleTitle title="Deployments">
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Deployments"
          slotDescription="Manage NIM deployments and their configurations."
          slotActions={
            <Flex gap="2">
              {docsButton}
              {createDeploymentButton}
            </Flex>
          }
        />
        <DeploymentsDataView
          workspace={workspace}
          onCreate={() => setIsCreateDeploymentOpen(true)}
          onDeploymentRowClick={(row) =>
            navigate(
              getWorkspaceDeploymentDetailsRoute(
                workspace,
                row.name,
                DEPLOYMENT_DETAILS_PANEL_VIEW_DETAILS
              ),
              { replace: true }
            )
          }
          onRequestDeleteDeployment={setDeploymentToDelete}
          attributes={{
            Stack: {
              className: 'h-full',
            },
          }}
        />
      </Stack>
      <CreateDeploymentSidePanel
        workspace={workspace}
        open={isCreateDeploymentOpen}
        prefill={createPrefill}
        onClose={() => {
          setIsCreateDeploymentOpen(false);
          // Drop the deep-link params so the panel doesn't keep reopening on rerenders.
          if (hasPrefillParams) {
            const next = new URLSearchParams(searchParams);
            next.delete('model');
            next.delete('fileset');
            setSearchParams(next, { replace: true });
          }
        }}
      />
      <DeploymentDetailsSidePanel
        open={detailsPanelOpen}
        deploymentName={deploymentNameFromPath}
        onClose={handleCloseDetailsPanel}
        onRequestDelete={setDeploymentToDelete}
      />
      {deploymentToDelete ? (
        <DeleteConfirmationModal
          open
          simpleConfirm
          onDelete={handleDeleteDeployment}
          title={`Delete deployment: ${deploymentToDelete.name}`}
          confirmationText={deploymentToDelete.name}
          successText="Deployment deletion started."
          errorText="Failed to start deleting the deployment. Please try again later."
          onClose={handleModalClose}
        />
      ) : null}
    </AccessibleTitle>
  );
};
