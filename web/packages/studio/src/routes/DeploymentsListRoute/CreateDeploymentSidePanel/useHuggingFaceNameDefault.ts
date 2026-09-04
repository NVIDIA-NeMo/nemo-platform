// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import {
  SOURCE_HF,
  type WizardFormValues,
} from '@studio/routes/DeploymentsListRoute/CreateDeploymentSidePanel/schema';
import { huggingFaceRepoIdToBaseName } from '@studio/routes/DeploymentsListRoute/huggingFaceDeploymentArtifacts';
import { useEffect } from 'react';
import { useFormState, useWatch, type Control, type UseFormSetValue } from 'react-hook-form';

/**
 * Keeps the wizard's Name field in step with the Hugging Face Repo ID.
 *
 * Applies only to the HuggingFace source; NGC and Workspace keep the random
 * `generateDefaultName()` default. Derivation stops for good once the user edits
 * the name themselves, so a deliberate choice is never overwritten mid-typing.
 */
export function useHuggingFaceNameDefault(
  control: Control<WizardFormValues>,
  setValue: UseFormSetValue<WizardFormValues>
): void {
  const source = useWatch({ control, name: 'source' });
  const repoId = useWatch({ control, name: 'repoId' });
  const { dirtyFields } = useFormState({ control });
  const nameEdited = Boolean(dirtyFields.name);

  useEffect(() => {
    if (source !== SOURCE_HF || nameEdited) return;

    const derived = huggingFaceRepoIdToBaseName(repoId ?? '');
    // Leave the existing default in place rather than blanking the field while the
    // user is still part-way through typing a repo ID.
    if (!derived) return;

    setValue('name', derived, { shouldDirty: false, shouldValidate: true });
  }, [nameEdited, repoId, setValue, source]);
}
