// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { PageHeader, Stack } from '@nvidia/foundations-react-core';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ANONYMIZER_ENABLED } from '@studio/constants/environment';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { FC } from 'react';

export const AnonymizerBuilderRoute: FC | null = ANONYMIZER_ENABLED
  ? () => {
      useBreadcrumbs({
        items: [{ slotLabel: 'Anonymizer' }, { slotLabel: 'Anonymize Data' }],
      });

      return (
        <AccessibleTitle title="Anonymize Data">
          <Stack className="h-full" gap="density-2xl" padding="density-2xl">
            <PageHeader
              className="p-0"
              slotHeading="Anonymize Data"
              slotDescription="Configure sources, entity detection, and masking strategy, then preview and run anonymization."
            />
          </Stack>
        </AccessibleTitle>
      );
    }
  : null;
