// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import { z } from 'zod';

/**
 * The form holds the whole guardrail document and nothing else.
 *
 * Every editable field — the instructions, the rails, their prompts — is a path inside
 * `config`. Keeping a flat copy of any of them alongside would mean two sources of truth
 * for the same key, and whichever one the save path didn't read would be silently
 * clobbered.
 */
export const guardrailFormSchema = z.object({
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
 * Build the working copy from the API config.
 *
 * Deep-cloned: react-query hands out the cached object and edits write into the working
 * copy in place, so sharing the reference would mutate the cache.
 */
export const mapConfigToForm = (data: RailsConfig | undefined): GuardrailFormValues => ({
  config: data ? structuredClone(data) : {},
});

/** The payload for PATCH. The working copy already is the whole document. */
export const applyFormToConfig = (values: GuardrailFormValues): RailsConfig => values.config;

/** Local-storage key for a config's draft, scoped by workspace and name. */
export const guardrailDraftKey = (workspace: string, name: string): string =>
  `guardrail-draft:${workspace}:${name}`;
