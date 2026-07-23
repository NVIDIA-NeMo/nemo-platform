// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button, PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ANONYMIZER_ENABLED } from '@studio/constants/environment';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getNewAnonymizerRoute } from '@studio/routes/utils';
import { FC } from 'react';
import { Link, Outlet } from 'react-router-dom';

export const AnonymizerListRoute: FC | null = ANONYMIZER_ENABLED
  ? () => {
      const workspace = useWorkspaceFromPath();

      useBreadcrumbs({ items: [{ slotLabel: 'Anonymizer' }] });

      return (
        <AccessibleTitle title="Anonymizer">
          <Stack className="h-full" gap="density-2xl" padding="density-2xl">
            <PageHeader
              className="p-0"
              slotHeading="Anonymizer"
              slotDescription="Detect and protect PII in your datasets through context-aware replacement and rewriting."
              slotActions={
                <Button asChild color="brand">
                  <Link to={getNewAnonymizerRoute(workspace)}>Anonymize Data</Link>
                </Button>
              }
            />
          </Stack>
          <Outlet />
        </AccessibleTitle>
      );
    }
  : null;
