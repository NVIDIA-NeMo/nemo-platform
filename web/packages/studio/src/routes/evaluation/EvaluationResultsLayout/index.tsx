// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AccessibleTitle } from '@nemo/common/src/components/AccessibleTitle';
import { PageHeader, Stack } from '@nvidia/foundations-react-core';
import { Loading } from '@studio/components/Layouts/Loading';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { FC, Suspense, useEffect } from 'react';
import { Outlet } from 'react-router';

export const EvaluationResultsLayout: FC = () => {
  const { setBreadcrumbs } = useBreadcrumbs();

  useEffect(() => {
    setBreadcrumbs([
      {
        slotLabel: 'Evaluations',
      },
    ]);
  }, [setBreadcrumbs]);

  return (
    <AccessibleTitle title="Evaluations">
      <Stack className="h-full overflow-auto" gap="density-2xl" padding="density-2xl">
        <PageHeader className="p-0" slotHeading="Evaluations" />
        <Suspense fallback={<Loading description="Loading..." />}>
          <Outlet />
        </Suspense>
      </Stack>
    </AccessibleTitle>
  );
};
