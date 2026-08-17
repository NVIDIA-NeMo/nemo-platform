// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import {
  getGeneralInstruction,
  setGeneralInstruction,
} from '@studio/routes/guardrails/GuardrailConfigTab/instructions';
import { z } from 'zod';

/**
 * The editable form model.
 *
 * `config` is the whole working copy of the guardrail document. Rails edit it wholesale —
 * switching one on writes a flow, a prompt, and sometimes a task model together — so a
 * flat field per setting cannot represent them. The two string fields stay flat because
 * they map to single values a text box can own.
 *
 * Anything neither the rails nor those fields touch rides along untouched, which is what
 * lets a config authored elsewhere survive a round trip (see {@link applyFormToConfig}).
 */
export const guardrailFormSchema = z.object({
  generalInstruction: z.string(),
  sampleConversation: z.string(),
  config: z.custom<RailsConfig>(() => true),
});

export type GuardrailFormValues = z.infer<typeof guardrailFormSchema>;

/** A locally-persisted draft, tagged with the server version it was branched from. */
export interface StoredDraft {
  /** The config's `updated_at` when the draft was taken, for stale detection. */
  baseVersion: string;
  values: GuardrailFormValues;
}

/**
 * Extract the form model from the API config.
 *
 * The working copy is deep-cloned: react-query hands out the cached object, and rails edit
 * the config in place, so sharing the reference would mutate the cache and leave the form
 * comparing a value against itself.
 */
export const mapConfigToForm = (data: RailsConfig | undefined): GuardrailFormValues => ({
  generalInstruction: getGeneralInstruction(data?.instructions),
  sampleConversation: data?.sample_conversation ?? '',
  config: data ? structuredClone(data) : {},
});

/**
 * Merge form values back onto the config, preserving every field we don't expose (models,
 * detectors, custom_data, …). This is the inverse of {@link mapConfigToForm} and the
 * single place the working copy becomes the payload.
 */
export const applyFormToConfig = (
  data: RailsConfig | undefined,
  values: GuardrailFormValues
): RailsConfig => {
  // Fall back to the server config so callers that only supply the flat fields — the
  // tests, and any caller predating the rails editor — keep working.
  const base = values.config ?? data ?? {};
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
