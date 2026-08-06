// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Sub-tab IDs for a guardrail's Test and Validate tab, used as both the tab
 * `value` and the trailing `/checks/<id>` URL segment.
 *
 * Kept out of the tab component so the route table can import these without
 * eagerly pulling in the lazily-loaded component.
 */
export enum GuardrailChecksSubTab {
  Tests = 'tests',
  Results = 'results',
}

export const GUARDRAIL_CHECKS_DEFAULT_SUB_TAB = GuardrailChecksSubTab.Tests;

export const isGuardrailChecksSubTab = (
  value: string | undefined
): value is GuardrailChecksSubTab =>
  Object.values(GuardrailChecksSubTab).includes(value as GuardrailChecksSubTab);
