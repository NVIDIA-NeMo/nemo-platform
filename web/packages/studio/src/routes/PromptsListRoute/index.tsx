// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { PromptsDataView } from '@studio/components/dataViews/PromptsDataView';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getWorkspacePromptsRoute } from '@studio/routes/utils';
import type { FC } from 'react';

export const PromptsListRoute: FC = () => {
  const workspace = useWorkspaceFromPath();

  useBreadcrumbs({
    items: [{ href: getWorkspacePromptsRoute(workspace), slotLabel: 'Prompts' }],
  });

  return (
    <AccessibleTitle title="Prompts">
      <Stack className="h-full" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Prompts"
          slotDescription="Manage reusable prompt templates for your workspace."
        />
        <PromptsDataView
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
