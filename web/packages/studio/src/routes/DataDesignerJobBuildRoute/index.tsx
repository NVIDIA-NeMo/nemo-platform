// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Flex, PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getDataDesignerJobListRoute, getNewDataDesignerJobRoute } from '@studio/routes/utils';
import type { FC } from 'react';

/**
 * Placeholder for the "Build from scratch" empty-canvas column builder. Reached from the
 * Create-a-fileset view's Continue action; the canvas itself is not wired up yet.
 */
export const DataDesignerJobBuildRoute: FC = () => {
  const workspace = useWorkspaceFromPath();

  useBreadcrumbs({
    items: [
      { href: getDataDesignerJobListRoute(workspace), slotLabel: 'Data Designer' },
      { href: getNewDataDesignerJobRoute(workspace), slotLabel: 'New fileset' },
      { slotLabel: 'Build from scratch' },
    ],
  });

  return (
    <AccessibleTitle title="Build from scratch">
      <Stack className="h-full" gap="density-2xl" padding="density-2xl">
        <PageHeader
          slotHeading="Build from scratch"
          slotDescription="Open an empty canvas and add columns block by block, your way."
        />
        <Flex
          align="center"
          justify="center"
          className="flex-1 rounded-md border border-dashed border-base"
        >
          <Text kind="body/regular/md" className="text-secondary">
            Empty canvas — the column builder is coming soon.
          </Text>
        </Flex>
      </Stack>
    </AccessibleTitle>
  );
};
