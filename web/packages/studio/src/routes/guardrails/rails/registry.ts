// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { selfCheckRail } from '@studio/routes/guardrails/rails/selfCheck';
import type { RailDefinition } from '@studio/routes/guardrails/rails/types';

/**
 * The rails Studio can configure, in the order they appear in the list.
 *
 * Deliberately hand-written rather than derived from the config schema: a rail is a set of
 * coordinated edits across `rails.*.flows`, `prompts[]` and `models[]`, and what each one
 * needs differs enough that generating the UI produces a form nobody can use. Adding a
 * rail means adding a definition here — see `selfCheck/` for the shape.
 *
 * Rails not yet defined here are still visible in the read-only sections below the list,
 * and remain fully intact in the saved config.
 */
export const RAIL_DEFINITIONS: RailDefinition[] = [selfCheckRail];
