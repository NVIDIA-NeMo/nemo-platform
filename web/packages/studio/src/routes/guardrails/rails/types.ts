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
  scopes: RailScope[];
  /** True when the rail is currently running, i.e. any of its flows are present. */
  isEnabled: (data: RailsConfig) => boolean;
  /**
   * Switch the rail on or off.
   *
   * Off removes the flows so the rail stops running, but keeps its prompts: a user who
   * has tuned a prompt should get it back when they switch the rail on again. Use
   * {@link clearSettings} to discard those too.
   */
  setEnabled: (data: RailsConfig, enabled: boolean) => RailsConfig;
  /** True when the rail is off but still holds settings that could be discarded. */
  hasStoredSettings: (data: RailsConfig) => boolean;
  /** Remove everything this rail owns, including anything {@link setEnabled} kept. */
  clearSettings: (data: RailsConfig) => RailsConfig;
  /** The rail's own trigger and whatever it opens. Omitted when a rail has no settings. */
  renderSettings?: (props: RailSettingsProps) => ReactNode;
}
