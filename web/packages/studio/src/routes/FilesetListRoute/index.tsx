// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getEntityReference } from '@nemo/common/src/namedEntity';
import { FilesetOutput } from '@nemo/sdk/generated/platform/schema';
import { Button, PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { DatasetsTable } from '@studio/components/DatasetsTable';
import { NewDatasetButton } from '@studio/components/NewDatasetButton';
import { NewModelFilesetButton } from '@studio/components/NewModelFilesetButton';
import { FILESET_DETAILS_ENABLED } from '@studio/constants/environment';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { ActionMenu } from '@studio/routes/FilesetListRoute/ActionMenu';
import { PanelManagement } from '@studio/routes/FilesetListRoute/PanelManagement';
import {
  getDatasetDetailRoute,
  getFilesetDetailsRoute,
  getNewFilesetRoute,
  getWorkspaceFilesetsRoute,
} from '@studio/routes/utils';
import { FC, useCallback } from 'react';
import { Link, Outlet, useNavigate } from 'react-router-dom';

export const FilesetListRoute: FC = () => {
  const navigate = useNavigate();
  const workspace = useWorkspaceFromPath();

  useBreadcrumbs({
    items: [{ href: getWorkspaceFilesetsRoute(workspace), slotLabel: 'Filesets' }],
  });

  const getDatasetRoute = useCallback(
    (dataset: FilesetOutput) => {
      // Bifurcate by purpose when the feature flag is on:
      //   dataset -> new dedicated detail page
      //   model   -> model detail page (owned by parallel team; helper not yet available -
      //              falls through to the side-panel URL until the model team's bead lands)
      //   other   -> existing side panel
      if (FILESET_DETAILS_ENABLED && dataset.purpose === 'dataset') {
        return getDatasetDetailRoute(workspace, dataset.name);
      }
      return getFilesetDetailsRoute(workspace, getEntityReference(dataset, { encode: true }));
    },
    [workspace]
  );

  const handleDatasetNav = useCallback(
    (dataset: FilesetOutput) => {
      navigate(getDatasetRoute(dataset));
    },
    [navigate, getDatasetRoute]
  );

  return (
    <AccessibleTitle title="Filesets">
      <Stack className="h-full" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Filesets"
          slotDescription="Filesets organize files by purpose — Generic, Dataset, or Model. Purpose determines which metadata fields are available and can't be changed after creation. Use Dataset for training and evaluation data, Model for model weights and checkpoints, and Generic for everything else."
          slotActions={
            FILESET_DETAILS_ENABLED ? (
              <>
                <NewDatasetButton color="brand" />
                <NewModelFilesetButton color="brand" />
              </>
            ) : (
              <Button asChild color="brand">
                <Link to={getNewFilesetRoute(workspace)}>Create Fileset</Link>
              </Button>
            )
          }
        />
        <DatasetsTable
          enableFilters
          enableBulkDelete
          enableSelection
          getDatasetRoute={getDatasetRoute}
          renderRowActions={(dataset, { onDatasetDeleted }) => (
            <ActionMenu
              dataset={dataset}
              onNavigateToDetails={handleDatasetNav}
              onDatasetDeleted={onDatasetDeleted}
            />
          )}
        />
      </Stack>
      <Outlet />
      <PanelManagement workspace={workspace} />
    </AccessibleTitle>
  );
};
