// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import {
  applyFormToConfig,
  type GuardrailFormValues,
} from '@studio/routes/guardrails/GuardrailForm/formModel';
import { useFormContext, useWatch } from 'react-hook-form';

export interface DraftRailsConfig {
  /** Whether the form holds edits not yet saved to the server. */
  isDirty: boolean;
  /**
   * Server config with the current form values applied. Equal to the saved config
   * when the form is pristine — callers that need "the draft, or nothing" should
   * gate on {@link isDirty}.
   */
  draftConfig: RailsConfig;
}

/**
 * The config as the user currently sees it: server data with live form edits merged in.
 *
 * Both tabs read this. The Configuration tab renders it; the checks tab sends it to
 * /checks when the run target is Draft. Deriving it twice would let a run exercise
 * something different from what the editor displays.
 */
export const useDraftRailsConfig = (): DraftRailsConfig => {
  const {
    control,
    formState: { isDirty },
  } = useFormContext<GuardrailFormValues>();
  const values = useWatch({ control }) as GuardrailFormValues;

  return { isDirty, draftConfig: applyFormToConfig(values) };
};
