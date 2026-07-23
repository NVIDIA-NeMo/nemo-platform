// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NewCustomizationForm } from '@studio/components/NewCustomizationForm';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getWorkspaceCustomizationJobListRoute } from '@studio/routes/utils';
import type { CustomizationJob } from '@studio/util/customizationBackend';
import { jobToFormFields } from '@studio/util/forms/customization';
import { useMemo } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';

interface NewCustomizationRouteState {
  cloneFromJob?: CustomizationJob;
}

export const NewCustomizationRoute = () => {
  const workspace = useWorkspaceFromPath();
  const [searchParams] = useSearchParams();
  const initialModel = searchParams.get('model') ?? undefined;

  const { state: locationState } = useLocation();
  const { cloneFromJob } = (locationState as NewCustomizationRouteState | null) ?? {};

  const initialValues = useMemo(
    () => (cloneFromJob ? jobToFormFields(cloneFromJob) : undefined),
    [cloneFromJob]
  );

  useBreadcrumbs({
    items: [
      {
        href: getWorkspaceCustomizationJobListRoute(workspace),
        slotLabel: 'Models',
      },
      {
        slotLabel: 'New Fine-Tuned Model',
      },
    ],
  });

  return (
    <NewCustomizationForm
      workspace={workspace}
      initialModel={initialModel}
      initialValues={initialValues}
    />
  );
};
