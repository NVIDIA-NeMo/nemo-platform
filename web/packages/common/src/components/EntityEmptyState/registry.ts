// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ShieldCheck, type LucideIcon } from 'lucide-react';

/**
 * A create call-to-action for a first-use empty state.
 *
 * Provide `to` for a route-driven create flow; the {@link EntityEmptyState}
 * navigates there on click. For modal-driven creates (no dedicated route),
 * omit `to` and pass `onCreate` at the callsite — the label still comes from
 * here so copy stays centralized.
 */
export interface EmptyStateCreateAction {
  label: string;
  to?: string;
}

/**
 * Per-entity copy, iconography, and self-service affordances for an empty
 * state. One entry per entity lives in {@link ENTITY_EMPTY_STATES}; callsites
 * never inline this content.
 */
export interface EmptyStateDescriptor {
  /** A `lucide-react` icon. The component applies the standard size token. */
  icon: LucideIcon;
  /** Sentence-case, entity-specific first-use heading. */
  heading: string;
  /** 1–2 sentences answering "why would I create one?". */
  subheading: string;
  /** Omit for entities with no in-app create flow (e.g. Agents, Members). */
  createAction?: EmptyStateCreateAction;
  /** Concrete, copy-pasteable CLI command with `<placeholder>` args. Omit when none exists. */
  cliCommand?: string;
  /** Copy-to-clipboard prompt that triggers the entity's skill. Omit when none exists. */
  skillPrompt?: string;
}

/** Keys of entities that have a standardized empty state. */
export type EntityKey = 'guardrails';

/**
 * Canonical empty-state registry. Grows one entry at a time as entities migrate
 * onto {@link EntityEmptyState}.
 */
export const ENTITY_EMPTY_STATES: Record<EntityKey, EmptyStateDescriptor> = {
  guardrails: {
    icon: ShieldCheck,
    heading: 'No guardrail configs yet',
    subheading:
      'Guardrail configs add content-safety, jailbreak, and PII rails to the models in this workspace.',
    // Create is a modal owned by the route, so the callsite supplies `onCreate`.
    createAction: { label: 'Create guardrail config' },
    cliCommand: 'nemo guardrail configs create <config-name>',
    skillPrompt: 'Help me create my first guardrail config with the nemo-guardrails skill',
  },
};
