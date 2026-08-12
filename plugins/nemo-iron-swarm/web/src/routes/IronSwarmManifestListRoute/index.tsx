// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { IronSwarmManifestsDataView } from '@iron-swarm/dataViews/IronSwarmManifestsDataView';
import { useBreadcrumbs, useWorkspace } from '@iron-swarm/host';
import { getIronSwarmRunListRoute, getNewIronSwarmManifestRoute } from '@iron-swarm/paths';
import { AccessibleTitle } from '@nemo/common';
import { Button, PageHeader, Stack } from '@nvidia/foundations-react-core';
import { FC } from 'react';
import { Link, Outlet } from 'react-router';

export const IronSwarmManifestListRoute: FC = () => {
  const workspace = useWorkspace();
  useBreadcrumbs({
    items: [
      { href: getIronSwarmRunListRoute(workspace), slotLabel: 'Iron Swarm' },
      { slotLabel: 'Manifests' },
    ],
  });

  return (
    <AccessibleTitle title="Iron Swarm Manifests">
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Manifests"
          slotDescription="Reusable war-game targets scaffolded from a deployed agent. Create one, then run the war-game against it."
          slotActions={
            <Button asChild color="brand">
              <Link to={getNewIronSwarmManifestRoute(workspace)}>New Manifest</Link>
            </Button>
          }
        />
        <IronSwarmManifestsDataView />
      </Stack>
      <Outlet />
    </AccessibleTitle>
  );
};
