// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AxeBuilder } from '@axe-core/playwright';
import type { Page } from '@playwright/test';

/**
 * WCAG 2.x conformance tags targeted by our accessibility harness.
 * Covers levels A and AA for WCAG 2.0, 2.1, and 2.2.
 */
const A11Y_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22a', 'wcag22aa'] as const;

/** Return type of a single axe scan — re-exported from @axe-core/playwright's analyze(). */
export type AxeScanResult = Awaited<ReturnType<AxeBuilder['analyze']>>;

/**
 * Runs an axe accessibility scan on the current page state.
 *
 * Returns the raw AxeResults so callers can assert on violations,
 * incomplete checks, or passes as appropriate for their test.
 */
export const runAxeScan = async (page: Page): Promise<AxeScanResult> =>
  new AxeBuilder({ page }).withTags([...A11Y_TAGS]).analyze();
