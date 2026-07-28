// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfigOutput } from '@nemo/sdk/generated/platform/schema';
import {
  getGeneralInstruction,
  setGeneralInstruction,
} from '@studio/routes/guardrails/GuardrailConfigTab/instructions';
import { z } from 'zod';

/**
 * The editable form model — a curated, flat subset of the guardrail config.
 * Fields are added here as they become editable; everything else in the config
 * rides along untouched (see {@link applyFormToConfig}).
 */
export const guardrailFormSchema = z.object({
  generalInstruction: z.string(),
  sampleConversation: z.string(),
});

export type GuardrailFormValues = z.infer<typeof guardrailFormSchema>;

/** A locally-persisted draft, tagged with the server version it was branched from. */
export interface StoredDraft {
  /** The config's `updated_at` when the draft was taken, for stale detection. */
  baseVersion: string;
  values: GuardrailFormValues;
}

/** Extract the form model from the API config. */
export const mapConfigToForm = (data: RailsConfigOutput | undefined): GuardrailFormValues => ({
  generalInstruction: getGeneralInstruction(data?.instructions),
  sampleConversation: data?.sample_conversation ?? '',
});

/**
 * Merge form values back onto the original server `data`, preserving every field
 * we don't expose (models, detectors, custom_data, …). This is the inverse of
 * {@link mapConfigToForm} and the single place each editable field is written back.
 */
export const applyFormToConfig = (
  data: RailsConfigOutput | undefined,
  values: GuardrailFormValues
): RailsConfigOutput => {
  const base = data ?? {};
  return {
    ...base,
    // Use the computed list directly: an empty result means the user cleared the
    // sole general instruction, so we must persist the removal rather than fall
    // back to the (still-populated) base instructions.
    instructions: setGeneralInstruction(base.instructions, values.generalInstruction),
    sample_conversation: values.sampleConversation === '' ? undefined : values.sampleConversation,
  };
};

/** Local-storage key for a config's draft, scoped by workspace and name. */
export const guardrailDraftKey = (workspace: string, name: string): string =>
  `guardrail-draft:${workspace}:${name}`;
