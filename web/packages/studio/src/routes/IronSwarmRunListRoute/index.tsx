// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { IronSwarmRunsDataView } from '@studio/components/dataViews/IronSwarmRunsDataView';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getIronSwarmManifestListRoute } from '@studio/routes/utils';
import { FC } from 'react';
import { Link, Outlet } from 'react-router-dom';

export const IronSwarmRunListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  useBreadcrumbs({ items: [{ slotLabel: 'Iron Swarm' }] });

  return (
    <AccessibleTitle title="Iron Swarm">
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Iron Swarm"
          slotDescription="Attack, defend, and validate war-game runs that harden your deployed agents."
          slotActions={
            <Button asChild color="brand">
              <Link to={getIronSwarmManifestListRoute(workspace)}>Manifests</Link>
            </Button>
          }
        />
        <IronSwarmRunsDataView />
      </Stack>
      <Outlet />
    </AccessibleTitle>
  );
};
