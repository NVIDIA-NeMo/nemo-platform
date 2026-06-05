// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { FC } from 'react';

/**
 * Empty landing page for the EXPERIMENT feature.
 *
 * Reached from the "Experiment" item in the Evaluate side-nav group and gated
 * behind the `experiment` feature flag (VITE_FF_EXPERIMENT, default false).
 */
export const ExperimentRoute: FC = () => {
  useBreadcrumbs({ items: [{ slotLabel: 'Experiment' }] });

  return (
    <AccessibleTitle title="Experiment">
      <Stack className="h-full" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Experiment"
          slotDescription="This is a placeholder landing page for the Experiment feature."
        />
      </Stack>
    </AccessibleTitle>
  );
};
