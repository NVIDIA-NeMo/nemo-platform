// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type { RailsConfig } from '@nemo/sdk/generated/platform/schema';
import type { ReactNode } from 'react';

/** A pipeline stage a rail can run at. */
export type RailScope = 'input' | 'output' | 'retrieval';

export interface RailSettingsProps {
  /** The working copy being edited. Rails are pure: they never touch the form directly. */
  data: RailsConfig;
  /** Replace the working copy. */
  onChange: (next: RailsConfig) => void;
}

/**
 * One guardrail, modelled explicitly.
 *
 * A rail in the config is not a single field — turning "self check" on means adding a flow
 * to `rails.input.flows`, and (for LLM-judged rails) a matching entry in `prompts[]`, and
 * sometimes a task LLM in `models[]`. The engine rejects the config if those disagree, so
 * a definition owns all of them together and exposes one on/off switch.
 *
 * Every function here is pure over `RailsConfig`, which keeps the coupling testable without
 * rendering anything.
 */
export interface RailDefinition {
  /** Stable id, used for React keys and the settings panel route. */
  id: string;
  /** Name shown in the rail list. */
  label: string;
  /** Stages this rail can run at, in pipeline order. Shown whether or not it is on. */
  scopes: readonly RailScope[];
  /**
   * True when the rail is running at this stage.
   *
   * The rail-level "is this on at all" is exactly `scopes.some(isScopeEnabled)`, so it is
   * derived by the list rather than declared here — two independent answers could
   * disagree, and the switch and the stage badges would then contradict each other.
   *
   * Total over {@link RailScope}: the list asks only about the rail's own `scopes`, but a
   * definition must answer `false` for any other stage rather than throw.
   */
  isScopeEnabled: (data: RailsConfig, scope: RailScope) => boolean;
  /**
   * Switch the rail on or off.
   *
   * Off removes the flows so the rail stops running, but keeps its prompts: a user who
   * has tuned a prompt should get it back when they switch the rail on again. Use
   * {@link clearSettings} to discard those too.
   */
  setEnabled: (data: RailsConfig, enabled: boolean) => RailsConfig;
  /**
   * True when the config holds settings this rail owns — regardless of whether it is
   * running. Callers decide when discarding is appropriate; the list only offers it for a
   * rail that is switched off, since {@link clearSettings} would otherwise stop a live one.
   */
  hasStoredSettings: (data: RailsConfig) => boolean;
  /** Remove everything this rail owns, including anything {@link setEnabled} kept. */
  clearSettings: (data: RailsConfig) => RailsConfig;
  /** The rail's own trigger and whatever it opens. Omitted when a rail has no settings. */
  renderSettings?: (props: RailSettingsProps) => ReactNode;
}
