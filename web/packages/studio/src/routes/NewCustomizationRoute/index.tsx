// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { CreateCustomizationStart } from '@studio/components/CreateCustomizationStart';
import type { StartSelection } from '@studio/components/CreateCustomizationStart/types';
import { NewCustomizationForm } from '@studio/components/NewCustomizationForm';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { getWorkspaceCustomizationJobListRoute } from '@studio/routes/utils';
import {
  isAutomodelSpec,
  isRlSpec,
  isUnslothSpec,
  type CustomizationJob,
} from '@studio/util/customizationBackend';
import { jobToFormFields, type CustomizationFormFields } from '@studio/util/forms/customization';
import { useMemo, useState } from 'react';
import { useLocation, useSearchParams } from 'react-router';

const isCloneFromJobState = (value: unknown): value is { cloneFromJob: CustomizationJob } => {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = (value as Record<string, unknown>).cloneFromJob;
  if (typeof candidate !== 'object' || candidate === null) return false;
  const spec = (candidate as Record<string, unknown>).spec;
  return isAutomodelSpec(spec) || isUnslothSpec(spec) || isRlSpec(spec);
};

export const NewCustomizationRoute = () => {
  const workspace = useWorkspaceFromPath();
  const [searchParams] = useSearchParams();
  const initialModel = searchParams.get('model') ?? undefined;

  const { state: locationState } = useLocation();
  const cloneFromJob = isCloneFromJobState(locationState) ? locationState.cloneFromJob : undefined;

  const clonedValues = useMemo(
    () => (cloneFromJob ? jobToFormFields(cloneFromJob) : undefined),
    [cloneFromJob]
  );

  // What the start screen resolved to. `null` means it is still being shown; a value
  // (possibly the empty object of "from scratch") means the form has taken over.
  const [started, setStarted] = useState<{ values?: CustomizationFormFields } | null>(null);

  // Arriving with a model to customize or a job to clone already says how to start, so
  // those entry points skip the picker rather than asking a question with a known answer.
  const isDeepLink = clonedValues !== undefined || initialModel !== undefined;

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

  const handleContinue = (selection: StartSelection) => {
    setStarted({ values: selection.optionId === 'scratch' ? undefined : selection.initialValues });
  };

  if (!isDeepLink && started === null) {
    return <CreateCustomizationStart workspace={workspace} onContinue={handleContinue} />;
  }

  return (
    <NewCustomizationForm
      workspace={workspace}
      initialModel={initialModel}
      initialValues={clonedValues ?? started?.values}
    />
  );
};
