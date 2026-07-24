// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NewCustomizationForm } from '@studio/components/NewCustomizationForm';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getWorkspaceCustomizationJobListRoute } from '@studio/routes/utils';
import {
  isAutomodelSpec,
  isUnslothSpec,
  type CustomizationJob,
} from '@studio/util/customizationBackend';
import { jobToFormFields } from '@studio/util/forms/customization';
import { useMemo } from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';

const isCloneFromJobState = (value: unknown): value is { cloneFromJob: CustomizationJob } => {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = (value as Record<string, unknown>).cloneFromJob;
  if (typeof candidate !== 'object' || candidate === null) return false;
  const spec = (candidate as Record<string, unknown>).spec;
  return isAutomodelSpec(spec) || isUnslothSpec(spec);
};

export const NewCustomizationRoute = () => {
  const workspace = useWorkspaceFromPath();
  const [searchParams] = useSearchParams();
  const initialModel = searchParams.get('model') ?? undefined;

  const { state: locationState } = useLocation();
  const cloneFromJob = isCloneFromJobState(locationState) ? locationState.cloneFromJob : undefined;

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
