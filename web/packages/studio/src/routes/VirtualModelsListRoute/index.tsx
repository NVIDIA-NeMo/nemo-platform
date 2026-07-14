// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { VirtualModelsDataView } from '@studio/components/dataViews/VirtualModelsDataView';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getWorkspaceVirtualModelsRoute } from '@studio/routes/utils';
import type { FC } from 'react';

export const VirtualModelsListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();

  useBreadcrumbs({
    items: [
      {
        href: getWorkspaceVirtualModelsRoute(workspace),
        slotLabel: 'Virtual Models',
      },
    ],
  });

  return (
    <AccessibleTitle title="Virtual Models">
      <Stack className="h-full" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Virtual Models"
          slotDescription="Inference routes that map model names to middleware pipelines."
        />
        <VirtualModelsDataView
          workspace={workspace}
          attributes={{
            Stack: {
              className: 'flex-1 min-h-0',
            },
          }}
        />
      </Stack>
    </AccessibleTitle>
  );
};
