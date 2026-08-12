// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AccessibleTitle } from '@nemo/common/src/components/AccessibleTitle';
import { Button, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { IronSwarmRunsDataView } from '@studio/components/dataViews/IronSwarmRunsDataView';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import {
  usePluginInstalled,
  usePluginsError,
  usePluginsLoaded,
} from '@studio/plugins/PluginContext';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getIronSwarmManifestListRoute } from '@studio/routes/utils';
import { CircleAlert } from 'lucide-react';
import { FC } from 'react';
import { Link, Outlet } from 'react-router';

export const IronSwarmRunListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();
  const pluginsLoaded = usePluginsLoaded();
  const pluginsError = usePluginsError();
  const ironSwarmInstalled = usePluginInstalled('iron-swarm');
  useBreadcrumbs({ items: [{ slotLabel: 'Iron Swarm' }] });

  if (!pluginsLoaded && !pluginsError) {
    return null;
  }

  if (pluginsLoaded && !pluginsError && !ironSwarmInstalled) {
    return (
      <Stack className="h-full justify-center mx-auto max-w-[640px]" gap="density-md">
        <CircleAlert className="size-16 stroke-2" color="var(--text-color-feedback-danger)" />
        <Text kind="display/xl">Plugin Not Enabled</Text>
        <Text kind="title/lg">The Iron Swarm plugin is not installed.</Text>
        <Text lineHeight="150">
          To use this page, the <strong>iron-swarm</strong> plugin must be registered with the
          platform. Ask your administrator to install and enable the iron-swarm plugin.
        </Text>
      </Stack>
    );
  }

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
