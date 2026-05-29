// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Banner } from '@nvidia/foundations-react-core';
import type { FC } from 'react';

interface AgentContextBannerProps {
  agentName: string;
  baselineModelUrn: string | null;
}

/**
 * Uses Kaizen's `Banner` with `info` status so the styling is design-system
 * native — no hand-rolled blue. The Apply action lives in the page-level CTA
 * cluster, not on the banner itself, to avoid two adjacent CTAs and to keep
 * the banner purely informational.
 */
export const AgentContextBanner: FC<AgentContextBannerProps> = ({
  agentName,
  baselineModelUrn,
}) => {
  return (
    <Banner status="info" kind="inline">
      Testing models for agent <strong>{agentName}</strong>. Baseline is locked to{' '}
      <span className="font-mono">{baselineModelUrn ?? '—'}</span>.
    </Banner>
  );
};
