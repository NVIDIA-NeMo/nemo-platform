// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  EntitiesPage,
  Entity,
  GuardrailCheckRequest,
  GuardrailCheckResponse,
  StatusEnum,
} from '@nemo/sdk/generated/platform/schema';

/** Entity type discriminator used in the entity-store for guardrail checks. */
export const GUARDRAIL_CHECKS_ENTITY_TYPE = 'guardrail_checks';

/** Verdict of a check or an individual rail. UI: success -> "Allowed", blocked -> "Guarded". */
export type Verdict = StatusEnum;

/** A single message in a check's conversation (user input, optional assistant output, etc.). */
export type GuardrailCheckMessage = GuardrailCheckRequest['messages'][number];

/** Per-rail verdict map returned by the /checks endpoint. */
export type RailsStatus = GuardrailCheckResponse['rails_status'];

/**
 * One guardrail a config declared at run time, and whether it actually reported a
 * verdict. Snapshotted onto each run: the config that produced a run is gone the
 * moment the user edits again, so deriving this at render time would describe
 * coverage that never ran.
 */
export interface ActivatedGuardrail {
  /** Dedupe identity (detector key, else the friendly label) and the only safe React key. */
  id: string;
  label: string;
  active: boolean;
}

/** One execution of a check against /checks, recorded on the check's history. */
export type RunRecord = {
  /** ISO 8601 timestamp of when the run completed. */
  run_at: string;
  /** Overall verdict for this run. */
  status: Verdict;
  /** Per-rail verdicts for this run. */
  rails_status: RailsStatus;
  /** Config ids reported by the run (from guardrails_data.config_ids). */
  config_ids?: string[];
  /** The parent config's db_version at run time, for honest history across config edits. */
  config_version?: number;
  /**
   * Set when the run targeted an unsaved draft rather than the saved config. Mutually
   * exclusive with `config_version` — a draft has no version to stamp.
   */
  is_draft?: boolean;
  /** Guardrail coverage of the config that ran. Absent on records written before this existed. */
  activated_guardrails?: ActivatedGuardrail[];
};

/** Studio-owned payload stored in a guardrail_checks entity's `data`. */
export type GuardrailCheckData = {
  /** The conversation to run through the guardrail: user input (+ optional assistant output). */
  messages: GuardrailCheckMessage[];
  /** Guardrails-specific options (e.g. config_ids). Model is inherited from the parent config. */
  guardrails?: GuardrailCheckRequest['guardrails'];
  /** Optional human description of the check. */
  description?: string;
  /** Run history, appended on each execution. */
  runs: RunRecord[];
};

/** `data` accepted when creating a check; `runs` defaults to []. */
export type GuardrailCheckDataInput = Omit<GuardrailCheckData, 'runs'> & { runs?: RunRecord[] };

/** A guardrail_checks entity — the entity-store envelope with a typed `data`. */
export type GuardrailCheckEntity = Omit<Entity, 'data'> & { data: GuardrailCheckData };

/** A page of guardrail check entities. */
export type GuardrailChecksPage = Omit<EntitiesPage, 'data'> & { data: GuardrailCheckEntity[] };
