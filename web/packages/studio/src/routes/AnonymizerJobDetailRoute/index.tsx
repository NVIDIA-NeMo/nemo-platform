// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PageHeader, Stack, Text } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ANONYMIZER_ENABLED } from '@studio/constants/environment';
import { ROUTE_PARAMS } from '@studio/constants/routes';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import type { FC } from 'react';
import { useParams } from 'react-router-dom';

export const AnonymizerJobDetailRoute: FC | null = ANONYMIZER_ENABLED
  ? () => {
      const { [ROUTE_PARAMS.anonymizerJobName]: jobName } = useParams();

      useBreadcrumbs({
        items: [{ slotLabel: 'Anonymizer' }, { slotLabel: jobName ?? 'Job' }],
      });

      return (
        <AccessibleTitle title={jobName ?? 'Anonymizer Job'}>
          <Stack className="h-full" gap="density-2xl" padding="density-2xl">
            <PageHeader className="p-0" slotHeading={jobName ?? 'Anonymizer Job'} />
            <Text kind="body/regular/md">Job details coming soon.</Text>
          </Stack>
        </AccessibleTitle>
      );
    }
  : null;
