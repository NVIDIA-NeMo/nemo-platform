// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { type FC } from 'react';

/** Placeholder for the experiment group detail page. */
export const ExperimentGroupDetailRoute: FC = () => {
  useBreadcrumbs({ items: [{ slotLabel: 'Experiments' }, { slotLabel: 'Detail' }] });

  return (
    <AccessibleTitle title="Experiment Group">
      <Stack className="h-full" gap="density-2xl" padding="density-2xl">
        <PageHeader
          className="p-0"
          slotHeading="Experiment Group"
          slotDescription="Experiment group detail page."
        />
      </Stack>
    </AccessibleTitle>
  );
};
