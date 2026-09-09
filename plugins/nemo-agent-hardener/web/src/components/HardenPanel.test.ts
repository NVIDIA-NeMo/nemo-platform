// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { canApplyMitigation } from '@agent-hardener/components/HardenPanel';

const params = (over: Partial<Parameters<typeof canApplyMitigation>[0]> = {}) => ({
  hasComposedGuardrails: true,
  manifestQuerySucceeded: true,
  isProjectSource: false,
  ...over,
});

describe('canApplyMitigation', () => {
  it('allows applying once guardrails are composed and the manifest is confirmed non-project', () => {
    expect(canApplyMitigation(params())).toBe(true);
  });

  it('disables while the manifest query is still loading', () => {
    expect(canApplyMitigation(params({ manifestQuerySucceeded: false }))).toBe(false);
  });

  it('disables when the manifest query failed, not just when it is loading', () => {
    // A failed query also leaves `manifestQuerySucceeded` false — the same guard covers both.
    expect(canApplyMitigation(params({ manifestQuerySucceeded: false, isProjectSource: false }))).toBe(
      false
    );
  });

  it('disables for a confirmed project-source manifest, which has no agent to adopt onto', () => {
    expect(canApplyMitigation(params({ isProjectSource: true }))).toBe(false);
  });

  it('disables when no guardrails have been composed yet', () => {
    expect(canApplyMitigation(params({ hasComposedGuardrails: false }))).toBe(false);
  });
});
