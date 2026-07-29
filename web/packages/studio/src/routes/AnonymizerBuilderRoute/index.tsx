// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { zodResolver } from '@hookform/resolvers/zod';
import { AccessibleTitle } from '@studio/components/AccessibleTitle';
import { ANONYMIZER_ENABLED } from '@studio/constants/environment';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { AnonymizerBuilderForm } from '@studio/routes/AnonymizerBuilderRoute/components/AnonymizerBuilderForm';
import {
  anonymizerFormSchema,
  getAnonymizerFormDefaults,
} from '@studio/routes/AnonymizerBuilderRoute/schema';
import type { FC } from 'react';
import { FormProvider, useForm } from 'react-hook-form';

export const AnonymizerBuilderRoute: FC | null = ANONYMIZER_ENABLED
  ? () => {
      useBreadcrumbs({
        items: [{ slotLabel: 'Anonymizer' }, { slotLabel: 'Anonymize Data' }],
      });

      const form = useForm({
        mode: 'onChange',
        resolver: zodResolver(anonymizerFormSchema),
        defaultValues: getAnonymizerFormDefaults(),
      });

      return (
        <AccessibleTitle title="Anonymize Data">
          <FormProvider {...form}>
            <AnonymizerBuilderForm />
          </FormProvider>
        </AccessibleTitle>
      );
    }
  : null;
