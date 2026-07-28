// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { GuardrailConfig } from '@nemo/sdk/generated/platform/schema';
import { createContext } from 'react';

/**
 * Guardrail-editing actions that live alongside the RHF form (which is provided
 * separately via `FormProvider`). Field state comes from `useFormContext`; this
 * carries the pieces RHF doesn't own — the server config and save/reset wiring.
 */
export interface GuardrailFormContextValue {
  /** The persisted server config the form is based on. */
  config: GuardrailConfig;
  /** Validate and PATCH the working copy back to the server. */
  save: () => void;
  /** Whether a save (PATCH) is in flight. */
  isSaving: boolean;
  /** Discard local edits and return the form to the server config. */
  resetToServer: () => void;
}

export const GuardrailFormContext = createContext<GuardrailFormContextValue | null>(null);
